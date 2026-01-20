import streamlit as st
import chromadb
from chromadb.config import Settings
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
import umap
import plotly.graph_objects as go
from plotly.graph_objects import Scatter3d, Scatter
import os

CHROMADB_PATH = "/data/chromadb"
COLLECTION_NAME = "tangerina_memory"

@st.cache_data
def extract_chromadb_data() -> Tuple[np.ndarray, List[Dict], List[str]]:
    try:
        if not os.path.exists(CHROMADB_PATH):
            return np.array([]), [], []
        
        client = chromadb.PersistentClient(
            path=CHROMADB_PATH,
            settings=Settings(anonymized_telemetry=False)
        )
        
        try:
            collection = client.get_collection(name=COLLECTION_NAME)
        except Exception:
            return np.array([]), [], []
        
        results = collection.get(include=['embeddings', 'documents', 'metadatas'])
        
        if not results or not results.get('ids') or len(results['ids']) == 0:
            return np.array([]), [], []
        
        embeddings_list = results.get('embeddings')
        if embeddings_list is None or len(embeddings_list) == 0:
            return np.array([]), [], []
        
        embeddings = np.array(embeddings_list)
        metadatas = results.get('metadatas', [])
        documents = results.get('documents', [])
        
        if embeddings.shape[0] == 0:
            return np.array([]), [], []
        
        return embeddings, metadatas, documents
    except Exception as e:
        st.error(f"Error extracting ChromaDB data: {e}")
        return np.array([]), [], []


@st.cache_data
def reduce_dimensions(embeddings: np.ndarray, method: str, n_components: int, random_state: int = 42) -> np.ndarray:
    if len(embeddings) == 0:
        return np.array([])
    
    try:
        if method == "umap":
            n_neighbors = min(15, len(embeddings) - 1)
            if n_neighbors < 2:
                n_neighbors = 2
            reducer = umap.UMAP(n_components=n_components, random_state=random_state, n_neighbors=n_neighbors, min_dist=0.1)
            reduced = reducer.fit_transform(embeddings)
        elif method == "tsne":
            perplexity = min(30, max(5, (len(embeddings) - 1) // 3))
            reducer = TSNE(n_components=n_components, random_state=random_state, perplexity=perplexity)
            reduced = reducer.fit_transform(embeddings)
        elif method == "pca":
            max_components = min(n_components, min(embeddings.shape))
            reducer = PCA(n_components=max_components, random_state=random_state)
            reduced = reducer.fit_transform(embeddings)
        else:
            raise ValueError(f"Unknown reduction method: {method}")
        
        return reduced
    except Exception as e:
        raise ValueError(f"Error in dimensionality reduction: {e}")


@st.cache_data
def build_knn_graph(embeddings: np.ndarray, k: int, similarity_threshold: float, metadatas: List[Dict]) -> nx.Graph:
    if len(embeddings) == 0:
        return nx.Graph()
    
    try:
        similarity_matrix = cosine_similarity(embeddings)
        
        G = nx.Graph()
        
        n = len(embeddings)
        k = min(k, n - 1)
        
        for i in range(n):
            similarities = similarity_matrix[i]
            top_k_indices = np.argsort(similarities)[::-1][1:k+1]
            
            for j in top_k_indices:
                similarity = similarities[j]
                if similarity >= similarity_threshold:
                    G.add_edge(i, j, weight=similarity)
            
            if metadatas and i < len(metadatas):
                metadata = metadatas[i] or {}
                if i not in G.nodes():
                    G.add_node(i)
                G.nodes[i]['guild_id'] = metadata.get('guild_id')
                G.nodes[i]['channel_id'] = metadata.get('channel_id')
                G.nodes[i]['user_id'] = metadata.get('user_id')
                G.nodes[i]['timestamp'] = metadata.get('timestamp')
            else:
                if i not in G.nodes():
                    G.add_node(i)
        
        return G
    except Exception as e:
        raise ValueError(f"Error building graph: {e}")


def create_plotly_graph(coords: np.ndarray, graph: nx.Graph, documents: List[str], 
                       metadatas: List[Dict], color_by: str, n_dimensions: int) -> go.Figure:
    if len(coords) == 0:
        fig = go.Figure()
        fig.add_annotation(text="No data available", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig
    
    edge_x = []
    edge_y = []
    edge_z = []
    
    for edge in graph.edges():
        x0, y0 = coords[edge[0]][0], coords[edge[0]][1]
        x1, y1 = coords[edge[1]][0], coords[edge[1]][1]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
        if n_dimensions == 3:
            z0, z1 = coords[edge[0]][2], coords[edge[1]][2]
            edge_z.extend([z0, z1, None])
    
    edge_trace = Scatter3d if n_dimensions == 3 else Scatter
    edge_kwargs = {
        'x': edge_x,
        'y': edge_y,
        'mode': 'lines',
        'line': dict(width=0.5, color='#888'),
        'hoverinfo': 'none',
        'showlegend': False
    }
    if n_dimensions == 3:
        edge_kwargs['z'] = edge_z
    
    edge_trace_obj = edge_trace(**edge_kwargs)
    
    node_x = coords[:, 0]
    node_y = coords[:, 1]
    node_z = coords[:, 2] if n_dimensions == 3 else None
    
    color_values_raw = []
    hover_texts = []
    
    for i in range(len(coords)):
        metadata = metadatas[i] if i < len(metadatas) else {}
        color_val = metadata.get(color_by, 'unknown') if metadata else 'unknown'
        color_values_raw.append(str(color_val))
        
        doc = documents[i] if i < len(documents) else ""
        doc_preview = doc[:100] + "..." if len(doc) > 100 else doc
        hover_text = f"Index: {i}<br>"
        hover_text += f"Document: {doc_preview}<br>"
        for key, value in metadata.items():
            hover_text += f"{key}: {value}<br>"
        hover_texts.append(hover_text)
    
    unique_categories = sorted(set(color_values_raw))
    category_to_index = {cat: idx for idx, cat in enumerate(unique_categories)}
    color_values = [category_to_index[val] for val in color_values_raw]
    
    node_sizes = [graph.degree(i) if i in graph.nodes() else 1 for i in range(len(coords))]
    node_sizes = [max(5, min(20, size * 2)) for size in node_sizes]
    
    node_trace = Scatter3d if n_dimensions == 3 else Scatter
    node_kwargs = {
        'x': node_x,
        'y': node_y,
        'mode': 'markers',
        'marker': dict(
            size=node_sizes,
            color=color_values,
            colorscale='Viridis',
            showscale=True,
            line=dict(width=0.5)
        ),
        'text': hover_texts,
        'hoverinfo': 'text',
        'name': 'Nodes'
    }
    if n_dimensions == 3:
        node_kwargs['z'] = node_z
    
    node_trace_obj = node_trace(**node_kwargs)
    
    fig = go.Figure(data=[edge_trace_obj, node_trace_obj])
    
    title = f"ChromaDB Multi-Dimensional Graph Visualization ({n_dimensions}D)"
    layout_kwargs = {
        'title': title,
        'showlegend': False,
        'hovermode': 'closest',
        'margin': dict(b=20, l=5, r=5, t=40),
        'annotations': [dict(
            text=f"Color by: {color_by}",
            showarrow=False,
            xref="paper", yref="paper",
            x=0.005, y=-0.002,
            xanchor="left", yanchor="bottom",
            font=dict(color="#888", size=12)
        )],
        'xaxis': dict(showgrid=False, zeroline=False, showticklabels=False),
        'yaxis': dict(showgrid=False, zeroline=False, showticklabels=False)
    }
    
    if n_dimensions == 3:
        layout_kwargs['scene'] = dict(
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            zaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
    
    fig.update_layout(**layout_kwargs)
    
    return fig


st.set_page_config(page_title="ChromaDB Visualization", layout="wide")

st.title("ChromaDB Multi-Dimensional Graph Visualization")

with st.spinner("Loading ChromaDB data..."):
    try:
        embeddings, metadatas, documents = extract_chromadb_data()
    except Exception as e:
        st.error(f"Failed to load ChromaDB data: {e}")
        st.stop()

if len(embeddings) == 0:
    st.warning("No data found in ChromaDB collection. The collection may be empty or not exist.")
    st.stop()

if len(metadatas) != len(embeddings) or len(documents) != len(embeddings):
    st.error("Data mismatch: embeddings, metadatas, and documents must have the same length.")
    st.stop()

st.info(f"Loaded {len(embeddings)} embeddings from ChromaDB")

if len(embeddings) > 10000:
    st.warning("Large dataset detected. Consider using sampling for better performance.")
    use_sampling = st.checkbox("Enable Sampling", value=True)
    if use_sampling:
        sample_size = st.slider("Sample Size", 100, min(10000, len(embeddings)), 1000)
        if sample_size > len(embeddings):
            sample_size = len(embeddings)
        indices = np.random.choice(len(embeddings), size=sample_size, replace=False)
        embeddings = embeddings[indices]
        metadatas = [metadatas[i] for i in indices]
        documents = [documents[i] for i in indices]
        st.info(f"Using {sample_size} samples for visualization")

unique_guild_ids = sorted(set([str(m.get('guild_id', '')) for m in metadatas if m and m.get('guild_id')]))
unique_channel_ids = sorted(set([str(m.get('channel_id', '')) for m in metadatas if m and m.get('channel_id')]))
unique_user_ids = sorted(set([str(m.get('user_id', '')) for m in metadatas if m and m.get('user_id')]))

with st.sidebar:
    st.header("Controls")
    
    reduction_method = st.selectbox(
        "Dimensionality Reduction Method",
        ["umap", "tsne", "pca"],
        index=0
    )
    
    n_dimensions = st.selectbox(
        "Dimensions",
        [2, 3],
        index=0
    )
    
    k_neighbors = st.slider(
        "k-NN",
        min_value=5,
        max_value=50,
        value=10,
        step=1,
        help="Number of nearest neighbors to connect in the graph"
    )
    
    similarity_threshold = st.slider(
        "Similarity Threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.7,
        step=0.05,
        help="Minimum cosine similarity to create an edge"
    )
    
    color_by = st.selectbox(
        "Color By",
        ["guild_id", "channel_id", "user_id", "timestamp"],
        index=0
    )
    
    st.header("Filters")
    
    filter_guild_id = st.selectbox(
        "Filter by Guild ID",
        ["All"] + unique_guild_ids,
        index=0
    )
    
    filter_channel_id = st.selectbox(
        "Filter by Channel ID",
        ["All"] + unique_channel_ids,
        index=0
    )
    
    filter_user_id = st.selectbox(
        "Filter by User ID",
        ["All"] + unique_user_ids,
        index=0
    )

filtered_indices = list(range(len(embeddings)))
if filter_guild_id != "All":
    filtered_indices = [i for i in filtered_indices if i < len(metadatas) and metadatas[i] and str(metadatas[i].get('guild_id', '')) == filter_guild_id]
if filter_channel_id != "All":
    filtered_indices = [i for i in filtered_indices if i < len(metadatas) and metadatas[i] and str(metadatas[i].get('channel_id', '')) == filter_channel_id]
if filter_user_id != "All":
    filtered_indices = [i for i in filtered_indices if i < len(metadatas) and metadatas[i] and str(metadatas[i].get('user_id', '')) == filter_user_id]

if len(filtered_indices) == 0:
    st.error("No data matches the selected filters.")
    st.stop()

if len(filtered_indices) < len(embeddings):
    embeddings = embeddings[filtered_indices]
    metadatas = [metadatas[i] for i in filtered_indices]
    documents = [documents[i] for i in filtered_indices]
    st.info(f"Filtered to {len(embeddings)} items")

with st.spinner("Reducing dimensions..."):
    try:
        coords = reduce_dimensions(embeddings, reduction_method, n_dimensions)
    except Exception as e:
        st.error(f"Error in dimensionality reduction: {e}")
        st.stop()

if len(coords) == 0:
    st.error("Dimensionality reduction failed.")
    st.stop()

with st.spinner("Building k-NN graph..."):
    try:
        graph = build_knn_graph(embeddings, k_neighbors, similarity_threshold, metadatas)
    except Exception as e:
        st.error(f"Error building graph: {e}")
        st.stop()

st.plotly_chart(create_plotly_graph(coords, graph, documents, metadatas, color_by, n_dimensions), 
                use_container_width=True)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Nodes", len(coords))
with col2:
    st.metric("Total Edges", graph.number_of_edges())
with col3:
    unique_colors = len(set([str(metadatas[i].get(color_by, 'unknown') if i < len(metadatas) and metadatas[i] else 'unknown') for i in range(len(coords))]))
    st.metric(f"Unique {color_by}", unique_colors)
with col4:
    avg_degree = sum(dict(graph.degree()).values()) / len(graph.nodes()) if len(graph.nodes()) > 0 else 0
    st.metric("Avg Node Degree", f"{avg_degree:.2f}")

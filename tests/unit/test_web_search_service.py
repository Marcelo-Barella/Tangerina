import pytest
from unittest.mock import MagicMock, patch
from chatbot.web_search_service import TavilyWebSearchService


@pytest.fixture
def mock_tavily_client():
    with patch('chatbot.web_search_service.TavilyClient') as mock:
        yield mock


@pytest.fixture
def web_search_service(mock_tavily_client):
    service = TavilyWebSearchService('test_api_key')
    return service


@pytest.mark.unit
class TestTavilyWebSearchServiceInit:
    def test_init_creates_client(self, mock_tavily_client):
        service = TavilyWebSearchService('test_api_key')

        mock_tavily_client.assert_called_once_with(api_key='test_api_key')
        assert service.client is not None


@pytest.mark.unit
class TestTavilyWebSearchServiceSearch:
    def test_search_success(self, web_search_service):
        mock_response = {
            'results': [
                {'title': 'Result 1', 'url': 'http://example.com/1', 'content': 'Content 1'},
                {'title': 'Result 2', 'url': 'http://example.com/2', 'content': 'Content 2'}
            ]
        }
        web_search_service.client.search = MagicMock(return_value=mock_response)

        result = web_search_service.search('test query')

        assert result['success'] is True
        assert len(result['results']) == 2
        assert result['results'][0]['title'] == 'Result 1'
        assert result['results'][0]['url'] == 'http://example.com/1'
        assert result['results'][0]['content'] == 'Content 1'
        assert result['error'] is None

    def test_search_with_max_results(self, web_search_service):
        mock_response = {
            'results': [
                {'title': f'Result {i}', 'url': f'http://example.com/{i}', 'content': f'Content {i}'}
                for i in range(10)
            ]
        }
        web_search_service.client.search = MagicMock(return_value=mock_response)

        result = web_search_service.search('test query', max_results=3)

        assert result['success'] is True
        assert len(result['results']) == 3
        web_search_service.client.search.assert_called_once_with(query='test query', max_results=3)

    def test_search_empty_query(self, web_search_service):
        result = web_search_service.search('')

        assert result['success'] is False
        assert result['results'] == []
        assert 'invalid' in result['error'].lower()

    def test_search_none_query(self, web_search_service):
        result = web_search_service.search(None)

        assert result['success'] is False
        assert result['results'] == []
        assert 'invalid' in result['error'].lower()

    def test_search_non_string_query(self, web_search_service):
        result = web_search_service.search(123)

        assert result['success'] is False
        assert result['results'] == []
        assert 'invalid' in result['error'].lower()

    def test_search_query_exceeds_400_chars(self, web_search_service):
        long_query = 'a' * 401
        result = web_search_service.search(long_query)

        assert result['success'] is False
        assert result['results'] == []
        assert '400 characters' in result['error']

    def test_search_query_exactly_400_chars(self, web_search_service):
        query_400 = 'a' * 400
        mock_response = {'results': []}
        web_search_service.client.search = MagicMock(return_value=mock_response)

        result = web_search_service.search(query_400)

        assert result['success'] is True

    def test_search_handles_missing_fields(self, web_search_service):
        mock_response = {
            'results': [
                {'title': 'Result 1'},
                {'url': 'http://example.com/2'},
                {'content': 'Content 3'}
            ]
        }
        web_search_service.client.search = MagicMock(return_value=mock_response)

        result = web_search_service.search('test query')

        assert result['success'] is True
        assert result['results'][0]['title'] == 'Result 1'
        assert result['results'][0]['url'] == ''
        assert result['results'][0]['content'] == ''
        assert result['results'][1]['title'] == ''
        assert result['results'][1]['url'] == 'http://example.com/2'

    def test_search_handles_empty_results(self, web_search_service):
        mock_response = {'results': []}
        web_search_service.client.search = MagicMock(return_value=mock_response)

        result = web_search_service.search('test query')

        assert result['success'] is True
        assert result['results'] == []
        assert result['error'] is None

    def test_search_handles_no_results_key(self, web_search_service):
        mock_response = {}
        web_search_service.client.search = MagicMock(return_value=mock_response)

        result = web_search_service.search('test query')

        assert result['success'] is True
        assert result['results'] == []

    def test_search_api_error(self, web_search_service):
        web_search_service.client.search = MagicMock(side_effect=Exception('API Error'))

        result = web_search_service.search('test query')

        assert result['success'] is False
        assert result['results'] == []
        assert 'API Error' in result['error']

    def test_search_api_timeout(self, web_search_service):
        web_search_service.client.search = MagicMock(side_effect=TimeoutError('Request timeout'))

        result = web_search_service.search('test query')

        assert result['success'] is False
        assert result['results'] == []
        assert 'timeout' in result['error'].lower()

    def test_search_respects_max_results_limit(self, web_search_service):
        mock_response = {
            'results': [
                {'title': f'Result {i}', 'url': f'http://example.com/{i}', 'content': f'Content {i}'}
                for i in range(20)
            ]
        }
        web_search_service.client.search = MagicMock(return_value=mock_response)

        result = web_search_service.search('test query', max_results=5)

        assert result['success'] is True
        assert len(result['results']) == 5

    def test_search_with_unicode_query(self, web_search_service):
        mock_response = {
            'results': [
                {'title': 'Resultado em português', 'url': 'http://example.com', 'content': 'Conteúdo'}
            ]
        }
        web_search_service.client.search = MagicMock(return_value=mock_response)

        result = web_search_service.search('pesquisa em português: café e coração')

        assert result['success'] is True
        assert len(result['results']) == 1
        assert 'Resultado em português' in result['results'][0]['title']

    def test_search_with_special_characters(self, web_search_service):
        mock_response = {'results': []}
        web_search_service.client.search = MagicMock(return_value=mock_response)

        result = web_search_service.search('query with @#$%^&* special chars')

        assert result['success'] is True

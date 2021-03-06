"""Contains the site structure discoverer spiderling."""
import logging
from typing import List, Tuple, Callable

from scrapy import Spider
from scrapy.http import Response

from scrapy_patterns.request_factory import RequestFactory
from scrapy_patterns.site_structure import SiteStructure


class CategoryParser:
    """Interface used for parsing categories."""
    def parse(self, response) -> List[Tuple[str, str]]:
        """
        Parses categories from the response.
        Args:
            response: The response

        Returns: List of tuples, where the first element is the URL of the category, and the second is the name.
        """
        raise NotImplementedError()


class SiteStructureDiscoverer:
    """Discovers the site structure."""
    # pylint: disable=too-many-arguments, too-many-instance-attributes
    def __init__(self, spider: Spider, start_url: str, category_parsers: List[CategoryParser],
                 request_factory: RequestFactory,
                 on_discovery_complete: Callable[['SiteStructureDiscoverer'], None] = None):
        """
        Args:
            spider: The spider to which this belongs.
            start_url: Starting URL of categories.
            category_parsers: List of category parsers for each level of categories.
            request_factory: The request factory.
            on_discovery_complete: An optional callback when the discovery is complete. It'll receive this discoverer
            as its argument. It should return a scrapy request to continue the scraping with.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.name = spider.name  # Needed to conform to Scrapy Spiders.
        self.structure = SiteStructure(self.name)
        self.__start_url = start_url
        self.__category_parsers = category_parsers
        self.__request_factory = request_factory
        self.__remaining_work = 0
        self.__on_discovery_complete = on_discovery_complete if on_discovery_complete else self.__do_nothing

    def create_start_request(self):
        """
        Creates the starting request.
        Returns: The starting request.
        """
        self.__remaining_work += 1
        return self.__request_factory.create(self.__start_url, self.__process_category_response,
                                             cb_kwargs={"category_index": 0, "path": None})

    def __process_category_response(self, response, category_index: int, path: str):
        self.__remaining_work -= 1
        category_parser = self.__category_parsers[category_index]
        urls_and_names = self.__get_urls_and_names(response, category_parser)
        requests = []
        for url, name in urls_and_names:
            structure_path = name if path is None else path + "/" + name
            self.structure.add_node_with_path(structure_path, url)
            if category_index + 1 < len(self.__category_parsers):
                request = self.__request_factory.create(
                    url, self.__process_category_response,
                    cb_kwargs={"category_index": category_index + 1, "path": structure_path})
                requests.append(request)
        self.__remaining_work += len(requests)
        self.logger.info("[%s] Remaining work(s): %d", self.name, self.__remaining_work)
        if self.__remaining_work == 0:
            self.logger.info("[%s] Discovery complete.\n"
                             "%s", self.name, str(self.structure))
            yield self.__on_discovery_complete(self)
        for req in requests:
            yield req

    @staticmethod
    def __get_urls_and_names(response: Response, category_parser: CategoryParser):
        return category_parser.parse(response)

    @staticmethod
    def __do_nothing(_):
        return None

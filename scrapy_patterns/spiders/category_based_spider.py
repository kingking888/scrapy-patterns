from typing import List, Optional
from scrapy import Spider
from recipes_scraper.patterns.spiders.private.category_based_spider_state import CategoryBasedSpiderState
from recipes_scraper.patterns.request_factory import RequestFactory
from recipes_scraper.patterns.spiderlings.site_structure_discoverer import SiteStructureDiscoverer, CategoryParser
from recipes_scraper.patterns.spiderlings.site_pager import SitePager, SitePageParsers
from recipes_scraper.patterns.site_structure import VisitState, Node


class CategoryBasedSpider(Spider):
    start_url = None
    request_factory = RequestFactory()

    def __init__(self, site_page_parsers: SitePageParsers, category_selectors: List[CategoryParser],
                 progress_file_dir: str,
                 name: str = None, start_url: str = None, request_factory: RequestFactory = None, **kwargs):
        super().__init__(name, **kwargs)
        if category_selectors is None:
            raise ValueError("%s must have category selectors" % type(self).__name__)
        if start_url is not None:
            self.start_url = start_url
        elif not getattr(self, "start_url", None):
            raise ValueError("%s must have start URL" % type(self).__name__)
        if request_factory is not None:
            self.request_factory = request_factory
        self.__category_selectors = category_selectors
        self.__spider_state = CategoryBasedSpiderState(self.name, progress_file_dir)
        self.__site_pager: Optional[SitePager] = None
        self.__site_page_parsers = site_page_parsers

    def start_requests(self):
        if self.__spider_state.is_loaded:
            self.__site_pager = self.__create_site_pager(self.__spider_state.current_page_url)
            yield self.__site_pager.create_start_request()
        else:
            site_discoverer = SiteStructureDiscoverer(self.name, self.start_url, self.__category_selectors,
                                                      self.request_factory, self._on_site_structure_discovery_complete)
            yield site_discoverer.create_start_request()

    def parse(self, response):
        # Not used
        yield None

    def _on_site_structure_discovery_complete(self, discoverer):
        self.__spider_state.site_structure = discoverer.structure
        self.__spider_state.save()
        return self.__progress_to_next_category()

    def __create_site_pager(self, start_url: str) -> SitePager:
        return SitePager(start_url, self, self.request_factory, self.__site_page_parsers,
                         self.__on_paging_finished, self.__on_page_finished)

    def __on_page_finished(self, next_page_url):
        # Category is not changed when a page is finished.
        self.__spider_state.current_page_url = next_page_url
        self.__spider_state.save()
        self.__spider_state.log()

    def __on_paging_finished(self):
        current_category_path = self.__spider_state.current_page_site_path
        current_category_node = self.__spider_state.site_structure.get_node_at_path(current_category_path)
        current_category_node.set_visit_state(VisitState.VISITED, propagate=False)
        self.__propagate_visited_if_siblings_visited(current_category_node)
        self.__spider_state.log()
        return self.__progress_to_next_category()

    def __progress_to_next_category(self):
        next_category = self.__spider_state.site_structure.find_leaf_with_visit_state(VisitState.NEW)
        if next_category:
            next_category.set_visit_state(VisitState.IN_PROGRESS, propagate=True)
            self.__site_pager = self.__create_site_pager(next_category.url)
            self.__spider_state.current_page_url = next_category.url
            self.__spider_state.current_page_site_path = next_category.get_path()
            self.__spider_state.save()
            self.__spider_state.log()
            return self.__site_pager.create_start_request()
        return None

    @staticmethod
    def __are_category_children_visited(category_node: Node):
        for child in category_node.children:
            if child.visit_state != VisitState.VISITED:
                return False
        return True

    def __propagate_visited_if_siblings_visited(self, category_node: Node):
        if category_node.parent and self.__are_category_children_visited(category_node.parent):
            category_node.parent.set_visit_state(VisitState.VISITED)
            self.__propagate_visited_if_siblings_visited(category_node.parent)

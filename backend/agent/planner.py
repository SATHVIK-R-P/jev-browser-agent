import re
from typing import List, Dict, Any, Optional

class TaskPlan:
    def __init__(self, initial_url: str, subgoals: List[str], search_query: Optional[str] = None):
        self.initial_url = initial_url
        self.subgoals = subgoals
        self.search_query = search_query
        self.current_subgoal_index = 0

    @property
    def current_subgoal(self) -> str:
        if 0 <= self.current_subgoal_index < len(self.subgoals):
            return self.subgoals[self.current_subgoal_index]
        return "Complete final goal verification and conclude task."

    def advance_subgoal(self):
        if self.current_subgoal_index < len(self.subgoals) - 1:
            self.current_subgoal_index += 1

class Planner:
    """
    Parses user natural-language tasks into structured execution plans,
    detecting starting domains, search queries, and milestone subgoals.
    """

    @staticmethod
    def create_plan(prompt: str) -> TaskPlan:
        p_lower = prompt.lower()

        # Check for explicit URLs
        url_match = re.search(r"https?://[^\s]+", prompt)
        if url_match:
            initial_url = url_match.group(0)
            subgoals = [f"Navigate to {initial_url}", "Analyze page structure", "Perform requested task"]
            return TaskPlan(initial_url=initial_url, subgoals=subgoals)

        # Example 1: Wikipedia tasks
        if "wikipedia" in p_lower:
            search_match = re.search(r"search for\s+([^\.]+)", prompt, re.IGNORECASE)
            query = search_match.group(1).strip() if search_match else "artificial intelligence"
            return TaskPlan(
                initial_url="https://www.wikipedia.org",
                search_query=query,
                subgoals=[
                    "Navigate to Wikipedia homepage",
                    f"Type '{query}' into Wikipedia search input",
                    "Click search submit or press Enter",
                    f"Read and verify '{query}' article page",
                    "Conclude task"
                ]
            )

        # Example 2: Search engine (Playwright / generic search)
        if "search engine" in p_lower or "search for python playwright" in p_lower:
            search_match = re.search(r"search for\s+([^\.]+)", prompt, re.IGNORECASE)
            query = search_match.group(1).strip() if search_match else "Python Playwright"
            return TaskPlan(
                initial_url="https://duckduckgo.com",
                search_query=query,
                subgoals=[
                    "Navigate to search engine",
                    f"Enter '{query}' into search input",
                    "Submit search query",
                    "Examine top search results",
                    "Click relevant result and conclude task"
                ]
            )

        # Example 3: Contact page
        if "contact" in p_lower:
            return TaskPlan(
                initial_url="https://news.ycombinator.com" if "website" in p_lower else "https://duckduckgo.com",
                subgoals=[
                    "Open target website",
                    "Locate contact link or navigation menu",
                    "Click contact page link",
                    "Verify contact details",
                    "Conclude task"
                ]
            )

        # Example 4: FastAPI docs
        if "fastapi" in p_lower:
            return TaskPlan(
                initial_url="https://duckduckgo.com",
                search_query="FastAPI official documentation",
                subgoals=[
                    "Open search engine",
                    "Search for FastAPI official documentation",
                    "Click official documentation link (fastapi.tiangolo.com)",
                    "Verify documentation homepage",
                    "Conclude task"
                ]
            )

        # Example 5: Shopping / laptops under 50,000
        if "laptop" in p_lower or "shopping" in p_lower or "50000" in p_lower or "50,000" in p_lower:
            return TaskPlan(
                initial_url="https://duckduckgo.com",
                search_query="laptops under 50000",
                subgoals=[
                    "Navigate to product search",
                    "Search for laptops under ₹50,000",
                    "Filter or sort by lowest price",
                    "Open cheapest matching laptop product",
                    "Verify laptop specifications and conclude task"
                ]
            )

        # Generic fallback plan
        search_query = prompt.replace("Open", "").replace("Search", "").strip()
        return TaskPlan(
            initial_url="https://duckduckgo.com",
            search_query=search_query,
            subgoals=[
                "Navigate to search engine",
                f"Search for '{search_query[:40]}'",
                "Inspect results and open matching page",
                "Conclude task"
            ]
        )

"""
Adjacent State \u2014 State for the Adjacent Market Analysis sub-graph.

Stores chat history, extracted context, parallel tool results, and the final 
Market Collision & Blindspot Report.
"""

from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class AdjacentState(TypedDict):
    """State for the adjacent market analysis pipeline.

    Attributes:
        messages: Chat message history.
        category: The business/product category being analyzed.
        fetched_content: Raw user-provided content.
        extracted_context: The structured core boundary definition of the product.
        
        # Parallel data collection fields
        tech_trends: Horizontal tech trends that could disrupt this vertical.
        adjacent_competitors: Neighboring products that could build this as a feature.
        startup_threats: Fundings/startups solving the same problem from a different angle.
        
        analysis_result: Final Market Collision & Blindspot Report.
    """

    messages: Annotated[list, add_messages]
    category: str
    fetched_content: list[str]
    
    extracted_context: str
    
    tech_trends: str
    adjacent_competitors: str
    startup_threats: str
    
    analysis_result: str

"""
Task type specific prompt hints.
These are additional instructions added to prompts based on the task evaluation type.
"""

TASK_TYPE_HINTS = {
    "url_match": """
=== NAVIGATION TASK ===
This task requires you to NAVIGATE to a specific page.
- You must click on the target item/product to go to its detail page
- Do NOT just stop with an answer containing the item name
- The task is complete only when you are on the correct URL
- After finding the target, click on it to navigate there
""",
    "string_match": """
=== INFORMATION RETRIEVAL TASK ===
This task requires you to FIND and REPORT specific information.
- Look carefully at ALL visible products/items on the page
- Make sure to include ALL required details in your answer
- When listing items, include their full names exactly as shown
- For price ranges, use the format '$X to $Y' (e.g. '$10.00 to $20.00'), do NOT use dashes
- Report the actual product prices, NOT filter options
- IGNORE filter UI controls - only examine actual product listings
- Use ```stop [your answer]``` when you have found the complete answer
""",
    "program_html": """
=== ACTION TASK ===
This task requires you to PERFORM an action on the website.
- Complete the required action (add to cart, add to wishlist, etc.)
- Navigate to the correct product first if needed
- The task is complete when the action has been successfully performed
- You may need to verify the action was completed
""",
}


def get_task_type_hint(eval_types: list) -> str:
    """
    Get the appropriate hint based on evaluation types.

    Args:
        eval_types: List of evaluation types, e.g., ['string_match'], ['url_match']

    Returns:
        Task-specific hint string to append to the prompt
    """
    if not eval_types:
        return ""

    # Use the first eval type as the primary hint
    primary_type = eval_types[0]
    return TASK_TYPE_HINTS.get(primary_type, "")


def get_spatial_hint(intent: str) -> str:
    """
    Detect spatial layout keywords in intent and provide targeted guidance.

    Args:
        intent: The task intent/objective string

    Returns:
        Additional spatial recognition hint if spatial keywords detected, empty string otherwise
    """
    spatial_keywords = [
        "row",
        "column",
        "first",
        "last",
        "top",
        "bottom",
        "left",
        "right",
    ]
    intent_lower = intent.lower()

    # Check if any spatial keyword is in the intent
    if any(keyword in intent_lower for keyword in spatial_keywords):
        return """

CRITICAL SPATIAL LAYOUT GUIDANCE:
Your task involves identifying items by their POSITION in a grid layout.
- A ROW = items at the same VERTICAL level (horizontal line of products)
- A COLUMN = items at the same HORIZONTAL level (vertical line of products)  
- "First row" = topmost products, "Last row" = bottommost products
- "First column" = leftmost products, "Last column" = rightmost products
- Look at the VISUAL GRID STRUCTURE, not just the order in the text
- IGNORE [FILTER] UI controls - only count actual product cards
- Count positions based on the visual layout you see
"""

    return ""

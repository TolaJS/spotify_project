"""Prompts for the Response Synthesis Agent."""

RESPONSE_SYNTHESIS_PROMPT = """You are synthesizing results from a Spotify assistant that can query listening history and perform live operations.

## Original User Request
{original_query}

## Execution Results
{execution_results}

## Task
Create a natural, conversational response that:
1. Directly answers the user's question or confirms the action taken
2. Combines information from multiple sources coherently (if applicable)
3. Highlights the most relevant information first
4. Uses specific details (artist names, track names, counts, etc.)
5. Is concise but complete

If the query involved chained operations (e.g., finding data then taking action), explain the connection naturally.

If any step failed, acknowledge it and explain what did work.

Response:"""


MULTI_RESULT_SYNTHESIS_PROMPT = """You are combining results from multiple queries about a user's Spotify data and operations.

## Original User Request
{original_query}

## Sub-queries and Results

{sub_query_results}

## Task
Synthesize these results into a single, coherent response that:
1. Addresses all parts of the user's original request
2. Flows naturally between topics
3. Avoids redundancy
4. Presents information in a logical order
5. Summarizes key findings

If some queries succeeded and others failed, present what worked and briefly note what didn't.

Response:"""


CHAINED_RESULT_SYNTHESIS_PROMPT = """You are explaining the result of a chained operation where data from listening history was used to perform a live Spotify action.

## Original User Request
{original_query}

## Step 1: Data Retrieved (from listening history)
{data_result}

## Step 2: Action Taken (live Spotify operation)
{action_result}

## Task
Create a response that:
1. Explains what was found in the user's listening history
2. Confirms the action that was taken based on that data
3. Connects the two naturally (e.g., "Based on your history, [X] is your top song, so I've added it to your queue")

Response:"""


ERROR_SYNTHESIS_PROMPT = """The user's request could not be fully completed.

## Original User Request
{original_query}

## What Happened
{error_details}

## Partial Results (if any)
{partial_results}

## Task
Create a helpful response that:
1. Acknowledges what went wrong in simple terms
2. Explains what (if anything) was accomplished
3. Suggests alternatives or next steps if appropriate

Be apologetic but not overly so. Focus on being helpful.

Response:"""

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

If Success is False, use the Interpretation field to understand what went wrong, but do NOT expose technical details like operation names, error codes, or internal system messages. Instead, translate the failure into a friendly, plain-language explanation (e.g. "I wasn't able to start playback" rather than "start_playback failed with NO_ACTIVE_DEVICE"). Where possible, suggest a practical fix the user can take (e.g. "Make sure Spotify is open and playing on one of your devices").

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

For any result where Success is False, use its Interpretation field to understand the cause, but describe it in friendly, plain language without mentioning error codes, operation names, or internal system details. Present what succeeded normally, then briefly explain each failure and suggest what the user can do about it.

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

If either step shows Success: False, use its Interpretation field to understand what went wrong, but do NOT mention error codes, operation names, or internal details. Describe the problem in plain, friendly language and suggest a practical fix where possible (e.g. "Make sure Spotify is open on one of your devices and try again").

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
1. Explains what went wrong in plain, friendly language — do NOT mention error codes, operation names, or internal system details. Translate the failure into something the user can understand (e.g. "I couldn't start playback" rather than "start_playback returned NO_ACTIVE_DEVICE").
2. Explains what (if anything) was still accomplished
3. Suggests a practical next step the user can take to resolve the issue

Be apologetic but not overly so. Focus on being helpful and clear.

Response:"""

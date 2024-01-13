import openai
import os

class Constraint:
    def __init__(self, constraint_type, details):
        self.type = constraint_type
        self.details = details

def natural_language_to_code(nl_query):
    try:
        print(f"Received NL query: {nl_query}")  # Debugging line

        system_prompt = "Convert natural language requests for a fantasy football lineup into Python constraint expressions. For example, if the request is 'I want Jalen Hurts as my QB', convert it into the format 'qb == \"jalen_hurts\"'."

        # Set your OpenAI API key
        api_key = os.environ.get("OPENAI_API_KEY")
        openai.api_key = api_key  # Set the API key

        # Sending the query to OpenAI's language model
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # Adjust model as needed
            messages=[
                {
                    "role": "system", 
                    "content": system_prompt
                },
                {
                    "role": "user", 
                    "content": nl_query
                }
            ],
            max_tokens=500  # Adjust as needed
        )

        # Extracting the Python constraint from the response
        generated_constraint = response['choices'][0]['message']['content'].strip()
        
        print(f"Generated constraint: {generated_constraint}")  # Debugging line

        return generated_constraint

    except Exception as e:
        print(f"An error occurred in natural_language_to_code: {e}")  # Debugging line
        return {"error": str(e)}

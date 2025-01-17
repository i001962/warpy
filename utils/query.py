import os
import re
from typing import Optional

import polars as pl
from dotenv import load_dotenv
from langchain.chat_models import ChatOpenAI
from langchain.schema import AIMessage, HumanMessage, SystemMessage
from rich import box
from rich.console import Console
from rich.panel import Panel
from sqlalchemy.engine import Engine

console = Console()

load_dotenv()


def remove_imports_from_models(model_str):
    start = model_str.index("class")
    return model_str[start:]


def get_sqlalchemy_models():
    with open("utils/models.py", "r") as f:
        sqlalchemy_models = f.read()
    return remove_imports_from_models(sqlalchemy_models)


def execute_raw_sql(engine: Engine, query: str) -> Optional[pl.DataFrame]:
    print()
    console.print(Panel(query, title="Running SQL", box=box.SQUARE, expand=False))
    print()

    with engine.connect() as con:
        if re.search(r"(?i)\b(insert|update|delete|drop)\b", query):
            user_confirmation = input(
                "This operation will modify or delete data. Are you sure you want to proceed? [y/N]: "
            )

            if user_confirmation.lower() != "y":
                print("Operation cancelled.")
                return None

            result = con.execute(query)
            print(f"{result.rowcount} rows affected.")
        else:
            result = con.execute(query)
            column_names = result.keys()
            data = [tuple(row) for row in result.fetchall()]
            df = pl.DataFrame(data, schema=column_names)
            return df


def execute_natural_language_query(
    engine: Engine, query: str
) -> Optional[pl.DataFrame]:
    chat = ChatOpenAI(temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))

    initial_prompt_raw = """
    Your job is to turn user queries (in natural language) to SQL. Only return the SQL and nothing else. Don't explain, don't say "here's your query." Just give the SQL. Say "Yes." if you understand.

    Timestamp is in unix millisecond format, anything timestamp related must be multiplied by 1000. The database is in SQLite, adjust accordingly. Here are the schema:
    """

    system_prompt = SystemMessage(
        content="You are a SQL writer. If the user asks about anything than SQL, deny. You are a very good SQL writer. Nothing else. Don't explain, don't say anything except the SQL."
    )

    initial_prompt = HumanMessage(
        content=f"{initial_prompt_raw}\n\n{get_sqlalchemy_models()}"
    )

    ai_response = AIMessage(content="Yes.")

    query_message = HumanMessage(content=query)

    messages = [system_prompt, initial_prompt, ai_response, query_message]
    print()
    console.print(Panel(query, title="Your query", box=box.SQUARE, expand=False))

    sql_query = chat(messages)
    return execute_raw_sql(engine, sql_query.content)


# def execute_advanced_query(query: str):
#     db = SQLDatabase.from_uri("sqlite:///datasets/datasets.db")
#     toolkit = SQLDatabaseToolkit(db=db)

#     chat = ChatOpenAI(temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))

#     agent_executor = create_sql_agent(
#         llm=chat,
#         toolkit=toolkit,
#         verbose=True,
#     )

#     prompt = f"Describe relevant tables, then {query}"
#     agent_executor.run(prompt)

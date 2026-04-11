import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.tools import tool
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SYSTEM_PROMPT = """შენ ხარ Aqua Clean-ის მხარდაჭერის ასისტენტი მესენჯერში.
პასუხები გაეცი მხოლოდ მოწოდებული კონტექსტიდან.
გამოიყენე თავაზიანი ფორმა და ბოლოს დაურთე 💙.

წესები:
- პასუხი უნდა იყოს გრამატიკულად სწორი და მოკლე.
- არასოდეს გაწყვიტო წინადადება ტოკენების ლიმიტის გამო — თუ ვერ ეტევა, შეამოკლე.
- ყოველთვის დაასრულე აზრი და არ გაწყვიტო პასუხი.
- მაქსიმუმ 2 მოკლე წინადადება. არანაირი გამონაკლისი.
- არ გამოიყენო სიები ან bullet points.
- არ გაიმეოროო კითხვა და არ დაწეროო შესავალი.
- პირდაპირ უპასუხე კითხვას."""

# Knowledge Base
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

if not os.path.exists("./db"):
    print("Initializing vectorstore from documents...")
    loader = DirectoryLoader("./data", glob="./*.txt", loader_cls=TextLoader, loader_kwargs={"encoding": "utf-8"})
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    splits = splitter.split_documents(docs)

    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory="./db"
    )
else:
    print("Loading existing vectorstore from disk...")
    vectorstore = Chroma(persist_directory="./db", embedding_function=embeddings)

RETRIEVER = vectorstore.as_retriever(search_kwargs={"k": 3})

# Tool for AI search
@tool
def search_page_info(query_input):
    """Searches the page's local database for info on products, prices, and FAQs."""

    if isinstance(query_input, dict):
        query = query_input.get("query", query_input.get("type", str(query_input)))
    else:
        query = query_input

    final_query = str(query)
    print(f"--- Debug: Searching database for: {final_query} ---")

    docs = RETRIEVER.invoke(final_query)
    return "\n\n".join([d.page_content for d in docs])


# Brain
def get_ai_answer(user_input: str) -> str:
    try:
        docs = RETRIEVER.invoke(user_input)
        context = "\n\n".join([d.page_content for d in docs])

        response = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            max_tokens=500,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"კონტექსტი:\n{context}\n\nკითხვა: {user_input}"}
            ]
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in get_ai_answer: {e}")
        return "ბოდიში, ამჟამად ტექნიკური პრობლემაა. გთხოვთ, მოგვიანებით სცადოთ. 💙"
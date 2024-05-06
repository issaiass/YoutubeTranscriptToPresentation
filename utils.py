from langchain.document_loaders import YoutubeLoader
from dotenv import load_dotenv, find_dotenv
from langchain_openai.chat_models import ChatOpenAI
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import PromptTemplate

from openai import OpenAI
import requests
import io

from slide_templates import (
    first_slide_template, 
    text_template, 
    context_template, 
    thanks_template
)

import time
import streamlit as st

load_dotenv(find_dotenv())


def get_youtube_details(url:str):
    loader = loader = YoutubeLoader.from_youtube_url(url, add_video_info=True)
    details = loader.load()
    return details

def document_text_split(details):
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=3000, chunk_overlap=0)
        documents_split = text_splitter.split_documents(details)
        return documents_split

def make_summary_chain():
     llm = ChatOpenAI(model_name='gpt-3.5-turbo', temperature=0.8, max_tokens=300)
     chain = load_summarize_chain(llm, chain_type='map_reduce', verbose=True)
     return chain

def get_chain_answer(chain, documents):
     answer = chain.run(documents)
     return answer


def base_chain():
    SYSTEM_TEMPLATE = """
    Answer the user's question based on the below context.
    The response must be explicit and restricted only to answer the question, don't start with 'the video explains' for example.
    <context>
    {context}
    </context>
    """
    llm = ChatOpenAI(model_name='gpt-3.5-turbo', temperature=0.8, max_tokens=300)    
    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_TEMPLATE,), MessagesPlaceholder(variable_name="messages"),])
    chain = create_stuff_documents_chain(llm=llm, prompt=prompt)
    return chain

def make_documents_response(documents, content):
    chain = base_chain()
    answer = chain.invoke({"context": documents, "messages": [HumanMessage(content=content)],})
    return answer


def per_document_response(documents, content):
    chain = base_chain()
    answer_list = [chain.invoke({"context": [doc], "messages": [HumanMessage(content=content)],}) for doc in documents]
    return answer_list


def generate_image_url(prompt):
    client = OpenAI()
    response = client.images.generate(
        model='dall-e-3',
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1
    )
    url = response.data[0].url
    return url 

def upload_file(client, url):
    obj = requests.get(url).content
    file = io.BytesIO(obj) 
    path = client.files.create(file=file, purpose='assistants')
    return path.id

def get_image_id(input_info, subtitle):
    client = OpenAI()
    prompt = PromptTemplate.from_template("""Given the content of the power point slides 
    <{input_info}> 
    create an inspirational photo that shows the theme 
    <{subtitle}> 
    this image will serve on a powerpoint slide show.
    """
    )
    
    url = generate_image_url(prompt=prompt.format(input_info=input_info, subtitle=subtitle))
    path_id = upload_file(client, url)
    return path_id

def create_assistant(client):
    assistant = client.beta.assistants.create(
        name="langchain_ppt_assistant",
        instructions="You are a data scientist and coder and will assist in a PowerPoint slide compendium via code.",
        tools=[{"type": "code_interpreter"}],
        model="gpt-4-1106-preview"
        )
    return assistant.id

def create_thread(client):
    thread = client.beta.threads.create()
    return thread.id


def submit_message(assistant_id, thread_id, user_message, model=None, file_ids=None):
    client = OpenAI()
    if model: 
        client.beta.assistants.update(assistant_id=assistant_id, model=model)

    params = {
        'thread_id': thread_id,
        'role': 'user',
        'content': user_message,
        }
    
    if file_ids:
        #client.beta.assistants.update(assistant_id=assistant_id, tool_resources={"code_interpreter":{"file_ids":file_ids}})        
        params['attachments'] = [{ "file_id": fid, "tools": [{"type": "code_interpreter"}]} for fid in file_ids]
        
    client.beta.threads.messages.create(**params) # create a thread
    return client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)

def get_response(client, thread_id):
    return client.beta.threads.messages.list(thread_id=thread_id)

def make_ppt(title_dict, introduction, slides_dict, conclusion):

    client = OpenAI()

    ppt_assistant_id = create_assistant(client)
    ppt_thread_id = create_thread(client)

    title_text, subtitle_text = title_dict['strings']
    title_text_img_id = title_dict['image_ids']

    slides_text = slides_dict['strings']
    slides_text_image_ids = slides_dict['image_ids']
    n_slides = len(slides_dict)
    
    file_ids = [title_text_img_id] + slides_text_image_ids

    user_message =  f"Use the included code template to create a PPTX slide that follows the template format, \
    but uses the image, slide title, and document subtitle included with this code template: \
    {first_slide_template}. IMPORTANT: Load the included image with id {title_text_img_id} in this message  as the image_path in \
    this first slide, and use the title {title_text} as the title_text variable,  use the subtitle_text {subtitle_text} a the subtitle_text variable. \
    NEXT, create a SECOND slide using the following code template: {text_template} to create a PPTX slide that follows the template format, but uses \
    the slide title {title_text} as slide_title variable, 'Introduction' as the slide_theme variable and {introduction} as the slide_text variable. \
    NEXT, create {n_slides+1} slides and add each one of subsequent slides to the previous slide, starting from the third slide use \
    the title {title_text} as title_text variable for all slides, but also " + ' '.join([f"for the slide number {k+1+2} use bullet points {slides_text[k]} as \
    bullet_point variable and load file with the image id {slides_text_image_ids[k]} in slide {k+1+2} as image_path variable, " for k in range(n_slides)]) + f"; \
    NEXT. starting from the slide {n_slides+1+2} using the following code template: {text_template} to create a PPTX slide that follows the template format, but \
    uses the slide title {title_text} as slide_title variable, 'Conclusion' as the slide_theme variable and {conclusion} as the slide_text variable. \
    FINALLY add the last slide using this code template: {thanks_template}"

    run = submit_message(assistant_id=ppt_assistant_id, thread_id=ppt_thread_id, user_message=user_message, file_ids=file_ids)

    while True:
        try:
            response = get_response(client=client, thread_id=ppt_thread_id)
            pptx_id = response.data[0].content[0].text.annotations[0].file_path.file_id
            st.write("Successfully retrieved slide show:", pptx_id)
            break
        except Exception as e:
            st.write("Assistant still working on PPTX...")
            time.sleep(10)
    print(pptx_id)
    ppt_file = client.files.content(pptx_id)
    obj = io.BytesIO(ppt_file.read())
    return obj
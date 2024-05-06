import streamlit as st
from utils import (
    get_youtube_details,
    document_text_split,
    make_summary_chain, 
    get_chain_answer, 
    make_documents_response, 
    per_document_response,
    get_image_id,
    make_ppt
)
import os


st.title(":orange[📹Youtube Video Transcript to Presentation 🖥️]")
st.markdown("#")

if os.environ.get('OPENAI_API_KEY'):
    yt_url = st.text_input("Youtube URL:", placeholder="Paste the Youtube URL here", key="input")
    # question = st.text_input(label='Write your question')    
    process_btn = st.button("Process")

if yt_url and process_btn:
    with st.spinner("Preparing Presentation"):
        details = get_youtube_details(url=yt_url)
        documents_split = document_text_split(details)

        # Title
        title = make_documents_response(documents_split, "Given the documents tell us an appropiate title")
        st.success(title)
        # subtitle
        subtitle = make_documents_response(documents_split, f"Make a subtitle for this title: {title}")
        st.success(subtitle)
        title_image_id = get_image_id(input_info=title, subtitle=subtitle)
        # introduction
        introduction = make_documents_response(documents_split, "Give me an short introduction.")
        st.success(introduction)
        # slides bullets
        slide_insights = per_document_response(documents_split, "Return only 3 key insights of the document in bullet points")
        slide_insights_image_ids = [get_image_id(input_info=insights, subtitle=subtitle) for insights in slide_insights]
        for slide_insight in slide_insights:
            st.write(slide_insight) 
        # conclusion
        chain = make_summary_chain()
        conclusion = get_chain_answer(chain, documents_split)
        st.write(conclusion)

        title_dict = dict(strings=[title, subtitle], image_ids=title_image_id)
        slides_dict = dict(strings=slide_insights, image_ids=slide_insights_image_ids)

        # make presentation with an agent
        ppt_obj = make_ppt(title_dict, introduction, slides_dict, conclusion)
        st.download_button('Download file', ppt_obj, file_name='presentation.pptx')
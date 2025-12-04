import streamlit as st
import pandas as pd
import requests
import feedparser
from newspaper import Article
import time

# --- 引入輕量化 NLP 套件 ---
import jieba
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer # 使用 LSA 演算法
# 也可以換成 LexRankSummarizer，效果也不錯

# --- 1. 頁面設定 ---
st.set_page_config(page_title="極速新聞摘要助手", page_icon="⚡", layout="wide")
st.title("⚡ 極速版 Google 新聞摘要 (CPU Friendly)")
st.markdown("使用 **LSA 演算法** 取代深度學習模型，實現 **毫秒級** 的快速摘要。")

# --- 2. 核心功能函式 ---

def search_google_news_rss(keyword, limit=5):
    """(維持不變) 使用 Google News RSS Feed 進行搜尋"""
    encoded_keyword = requests.utils.quote(keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(rss_url)
    
    news_list = []
    for entry in feed.entries[:limit]:
        real_url = get_actual_url(entry.link)
        if real_url:
            news_list.append({
                "title": entry.title,
                "link": real_url,
                "published": entry.published
            })
    return news_list

def get_actual_url(google_url):
    """(維持不變) 解析真實 URL"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.head(google_url, allow_redirects=True, headers=headers, timeout=5)
        return response.url
    except:
        return None

def sumy_summarize(text, sentence_count=3):
    """
    使用 Sumy + Jieba 進行中文萃取式摘要
    """
    try:
        # 1. 中文前處理：因為 sumy 預設是以空白分詞，中文需要先用 jieba 切開
        # 例如："今天天氣很好" -> "今天 天氣 很好"
        seg_list = jieba.cut(text)
        text_segmented = " ".join(seg_list)
        
        # 2. 建立 Parser
        parser = PlaintextParser.from_string(text_segmented, Tokenizer("english")) 
        # 這裡借用 english tokenizer，因為我們已經手動用空白切開中文詞彙了
        
        # 3. 初始化摘要器 (LSA)
        summarizer = LsaSummarizer() 
        
        # 4. 執行摘要，取出最重要的 N 個句子
        summary_sentences = summarizer(parser.document, sentence_count)
        
        # 5. 組合結果 (還原成不帶空白的中文)
        result = ""
        for sentence in summary_sentences:
            # sumy 的 sentence 物件轉字串後會有空白，我們把它去掉 (簡單處理)
            raw_sent = str(sentence).replace(" ", "")
            result += raw_sent + "。"
            
        return result
        
    except Exception as e:
        return f"摘要錯誤: {e}"

def extract_and_process(url):
    """抓取並摘要"""
    try:
        article = Article(url)
        article.download()
        article.parse()
        
        if len(article.text) < 50:
             return "文章內容太短"

        # 使用 Sumy 進行摘要 (只要 0.01秒)
        summary = sumy_summarize(article.text, sentence_count=3)
        return summary
        
    except Exception as e:
        return f"無法讀取: {str(e)}"

# --- 3. 主程式邏輯 ---

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("輸入關鍵字", placeholder="例如：台積電、輝達...")
    with col2:
        submit_button = st.form_submit_button(label='🚀 極速搜尋')

if submit_button and keyword:
    st.divider()
    
    # 這裡不需要進度條了，因為速度會非常快
    with st.spinner('正在光速搜尋與摘要中...'):
        news_items = search_google_news_rss(keyword)
        
        results_data = []
        for item in news_items:
            # 抓取 + 摘要
            summary = extract_and_process(item['link'])
            
            results_data.append({
                "新聞標題": item['title'],
                "重點摘要 (LSA萃取)": summary,
                "原始連結": item['link']
            })
            
    # 直接顯示結果
    if results_data:
        st.success(f"已完成！共找到 {len(results_data)} 篇新聞。")
        df = pd.DataFrame(results_data)
        st.dataframe(
            df,
            column_config={
                "原始連結": st.column_config.LinkColumn("原始連結", display_text="🔗 閱讀原文"),
                "重點摘要 (LSA萃取)": st.column_config.TextColumn("重點摘要", width="large")
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.warning("找不到相關新聞。")
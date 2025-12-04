import streamlit as st
import pandas as pd
from duckduckgo_search import DDGS
from newspaper import Article, Config
import jieba
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

# --- 1. 頁面設定 ---
st.set_page_config(page_title="AI 新聞摘要助手", page_icon="🌍", layout="wide")
st.title("🌍 AI 全球新聞搜尋與摘要 (直連版)")
st.markdown("使用 **DuckDuckGo** 獲取直連網址，搭配 **LSA 演算法** 進行極速摘要。")

# --- 2. 核心功能函式 ---

def sumy_summarize(text, sentence_count=3):
    """使用 Sumy + Jieba 進行中文萃取式摘要"""
    try:
        if not text: return "無內容"
        
        # 中文斷詞處理
        seg_list = jieba.cut(text)
        text_segmented = " ".join(seg_list)
        
        # 初始化摘要器
        parser = PlaintextParser.from_string(text_segmented, Tokenizer("english")) 
        summarizer = LsaSummarizer() 
        summary_sentences = summarizer(parser.document, sentence_count)
        
        # 組合結果
        result = ""
        for sentence in summary_sentences:
            raw_sent = str(sentence).replace(" ", "")
            result += raw_sent + "。"
        return result
    except Exception as e:
        return f"摘要錯誤: {e}"

def extract_and_process(url):
    """
    抓取並摘要
    """
    try:
        # 設定偽裝瀏覽器 User-Agent
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        config.request_timeout = 10
        
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        # 如果正文太短，改抓 Meta Description
        if len(article.text) < 50:
             if article.meta_description and len(article.meta_description) > 10:
                 return f"📌 (來源簡介) {article.meta_description}"
             return "⚠️ 無法抓取內容 (網站阻擋爬蟲)"

        # 執行摘要
        summary = sumy_summarize(article.text, sentence_count=3)
        return summary
        
    except Exception as e:
        return f"❌ 處理錯誤: {str(e)}"

def search_news_ddg(keyword, limit=5):
    """
    使用 DuckDuckGo 搜尋新聞 (直接提供真實連結，無需解碼)
    """
    results = []
    try:
        with DDGS() as ddgs:
            # region='wt-wt' 表示全球，也可以設 'tw-zh' 針對台灣
            ddgs_news = ddgs.news(keywords=keyword, region='wt-wt', safebesearch='off', max_results=limit)
            
            for r in ddgs_news:
                results.append({
                    "title": r['title'],
                    "link": r['url'], # DuckDuckGo 直接給出真實連結
                    "source": r['source'],
                    "date": r['date']
                })
    except Exception as e:
        st.error(f"搜尋錯誤: {e}")
    return results

# --- 3. 主程式邏輯 ---

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("輸入關鍵字", placeholder="例如：OpenAI, 台積電...")
    with col2:
        submit_button = st.form_submit_button(label='🚀 搜尋')

if submit_button and keyword:
    st.divider()
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    progress_text.text(f"🔍 正在搜尋「{keyword}」...")
    news_items = search_news_ddg(keyword)
    
    if not news_items:
        st.warning("找不到相關新聞，請稍後再試或更換關鍵字。")
        progress_bar.empty()
    else:
        results_data = []
        total = len(news_items)
        
        for i, item in enumerate(news_items):
            progress_text.text(f"正在處理 ({i+1}/{total}): {item['title']} ...")
            progress_bar.progress((i + 1) / total)
            
            # 直接使用 link，因為這是真實網址
            summary = extract_and_process(item['link'])
            
            results_data.append({
                "新聞標題": item['title'],
                "來源": item['source'],
                "AI 重點摘要": summary,
                "連結": item['link']
            })
        
        progress_bar.empty()
        progress_text.empty()
        
        st.success("✅ 完成！")
        
        df = pd.DataFrame(results_data)
        st.dataframe(
            df,
            column_config={
                "連結": st.column_config.LinkColumn("連結", display_text="🔗 前往閱讀"),
                "AI 重點摘要": st.column_config.TextColumn("AI 重點摘要", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )
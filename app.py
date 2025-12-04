import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from newspaper import Article, Config
import jieba
import nltk

# --- 1. NLTK 自動修復 (雲端環境必備) ---
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab', quiet=True)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

# --- 2. 頁面設定 ---
st.set_page_config(page_title="Yahoo 財經新聞摘要", page_icon="📈", layout="wide")
st.title("📈 Yahoo 財經新聞 AI 摘要")
st.markdown("來源：**Yahoo 股市** | 技術：**LSA 演算法** + **Python 爬蟲**")

# --- 3. 核心功能函式 ---

def sumy_summarize(text, sentence_count=3):
    """使用 Sumy + Jieba 進行中文萃取式摘要"""
    try:
        if not text: return "無內容"
        seg_list = jieba.cut(text)
        text_segmented = " ".join(seg_list)
        parser = PlaintextParser.from_string(text_segmented, Tokenizer("english")) 
        summarizer = LsaSummarizer() 
        summary_sentences = summarizer(parser.document, sentence_count)
        
        result = ""
        for sentence in summary_sentences:
            raw_sent = str(sentence).replace(" ", "")
            result += raw_sent + "。"
        return result
    except Exception as e:
        return f"摘要錯誤: {e}"

def extract_and_process(url):
    """
    抓取並摘要 Yahoo 新聞
    Yahoo 的連結通常很乾淨，直接爬取即可。
    """
    try:
        # 設定偽裝瀏覽器
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        config.request_timeout = 10
        
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        # 檢查內容長度
        if len(article.text) < 50:
             return "⚠️ 內容過短或非新聞格式 (可能是影片或圖表)", url

        # 執行摘要
        summary = sumy_summarize(article.text, sentence_count=3)
        return summary, url
        
    except Exception as e:
        return f"❌ 處理錯誤: {str(e)}", url

def scrape_yahoo_finance(keyword, limit=5):
    """
    爬取 Yahoo 股市搜尋結果
    參考自: LearnCodeWithMike (針對搜尋頁面改寫)
    """
    results = []
    try:
        # Yahoo 股市搜尋 URL
        url = f"https://tw.stock.yahoo.com/search?p={keyword}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 策略：抓取頁面中所有看起來像新聞的連結
        # Yahoo 搜尋頁面結構比較雜，我們找 href 包含 "/news/" 的連結
        # 並且排除重複的
        
        seen_links = set()
        count = 0
        
        # 抓取所有連結
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link['href']
            title = link.get_text().strip()
            
            # 篩選條件：
            # 1. 連結包含 '/news/' (代表是新聞)
            # 2. 標題長度大於 10 (過濾掉無意義的按鈕)
            # 3. 不在已抓取清單中
            if '/news/' in href and len(title) > 10 and href not in seen_links:
                
                # 處理相對路徑 (雖然 Yahoo 通常給絕對路徑，保險起見)
                if not href.startswith('http'):
                    href = 'https://tw.stock.yahoo.com' + href
                
                results.append({
                    "title": title,
                    "link": href
                })
                seen_links.add(href)
                count += 1
                
                if count >= limit:
                    break
                    
    except Exception as e:
        st.error(f"Yahoo 爬蟲發生錯誤: {e}")
        
    return results

# --- 4. 主程式介面 ---

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("輸入金融關鍵字", placeholder="例如：台積電、ETF、高股息...")
    with col2:
        submit_button = st.form_submit_button(label='🚀 搜尋 Yahoo')

if submit_button and keyword:
    st.divider()
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    progress_text.text(f"🔍 正在爬取 Yahoo 股市：「{keyword}」...")
    
    # 1. 爬取
    news_items = scrape_yahoo_finance(keyword, limit=5)
    
    if not news_items:
        st.warning("找不到相關新聞，Yahoo 搜尋頁面結構可能已更新，或無相關資料。")
        progress_bar.empty()
    else:
        results_data = []
        total = len(news_items)
        
        for i, item in enumerate(news_items):
            progress_text.text(f"正在處理 ({i+1}/{total}): {item['title'][:15]}...")
            progress_bar.progress((i + 1) / total)
            
            # 2. 摘要
            summary, real_url = extract_and_process(item['link'])
            
            results_data.append({
                "新聞標題": item['title'],
                "AI 重點摘要": summary,
                "連結": real_url
            })
        
        progress_bar.empty()
        progress_text.empty()
        
        st.success(f"✅ 完成！共找到 {total} 篇相關報導。")
        
        df = pd.DataFrame(results_data)
        st.dataframe(
            df,
            column_config={
                "連結": st.column_config.LinkColumn("連結", display_text="🔗 前往 Yahoo"),
                "AI 重點摘要": st.column_config.TextColumn("AI 重點摘要", width="large"),
            },
            hide_index=True,
            use_container_width=True
        )
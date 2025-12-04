import streamlit as st
import pandas as pd
import requests
from newspaper import Article, Config
import nltk
from concurrent.futures import ThreadPoolExecutor, as_completed
from deep_translator import GoogleTranslator # 新增翻譯工具

# --- 1. NLTK 自動修復 ---
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
st.set_page_config(page_title="Massive 金融新聞 (中譯版)", page_icon="🏦", layout="wide")
st.title("🏦 Massive 美股新聞摘要")
st.markdown("來源：**Massive (Polygon)** | 核心：**LSA 摘要** + **自動翻譯** + **多執行緒加速**")
st.info("💡 提示：輸入美股代號 (例如 **TSM**, **NVDA**, **AAPL**)")

# --- 3. API Key ---
MASSIVE_API_KEY = "vMnBeXpL5XKK4G1nuf2jmXR9B2wXuC15"

# --- 4. 核心功能函式 ---

def translate_to_chinese(text):
    """
    使用 deep-translator 快速將英文轉中文
    """
    try:
        # source='auto' 自動偵測, target='zh-TW' 繁體中文
        translated = GoogleTranslator(source='auto', target='zh-TW').translate(text)
        return translated
    except Exception:
        return text # 如果翻譯失敗，回傳原文

def sumy_summarize(text, sentence_count=3):
    try:
        if not text: return "無內容"
        
        # 英文斷詞 (Massive 來源主要是英文)
        parser = PlaintextParser.from_string(text, Tokenizer("english")) 
        summarizer = LsaSummarizer() 
        summary_sentences = summarizer(parser.document, sentence_count)
        
        # 組合英文摘要
        english_summary = " ".join([str(sentence) for sentence in summary_sentences])
        
        # --- 翻譯成中文 ---
        if english_summary:
            chinese_summary = translate_to_chinese(english_summary)
            return chinese_summary
        
        return "無法產生摘要"
    except Exception as e:
        return f"摘要錯誤: {e}"

def extract_and_process(item):
    """
    單篇文章處理流程 (下載 -> 摘要 -> 翻譯)
    """
    url = item.get('article_url')
    title = item.get('title')
    publisher = item.get('publisher', {}).get('name', 'Unknown')
    pub_time = item.get('published_utc', '')[:10]
    
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
        config.request_timeout = 5 # 縮短超時設定以加快速度
        
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        if len(article.text) < 50:
             # 如果內文太短，嘗試翻譯 API 給的 description
             desc = item.get('description', '')
             if desc:
                 return {
                     "新聞標題": title,
                     "媒體來源": publisher,
                     "AI 重點摘要": f"📌 (官方摘要) {translate_to_chinese(desc)}",
                     "發布時間": pub_time,
                     "連結": url
                 }
             return None

        # 執行摘要 + 翻譯
        summary = sumy_summarize(article.text, sentence_count=3)
        
        return {
            "新聞標題": title,
            "媒體來源": publisher,
            "AI 重點摘要": summary,
            "發布時間": pub_time,
            "連結": url
        }
        
    except Exception as e:
        return None

def search_massive_news(ticker, limit=5):
    try:
        url = "https://api.polygon.io/v2/reference/news"
        params = {
            'ticker': ticker.upper(),
            'limit': limit,
            'apiKey': MASSIVE_API_KEY,
            'sort': 'published_utc',
            'order': 'desc'
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return data.get('results', [])
    except Exception as e:
        st.error(f"連線錯誤: {e}")
        return []

# --- 5. 主程式介面 ---

with st.form(key='search_form'):
    col1, col2 = st.columns([3, 1])
    with col1:
        keyword = st.text_input("輸入美股代號 (Ticker)", value="TSM")
    with col2:
        submit_button = st.form_submit_button(label='🚀 搜尋')

if submit_button and keyword:
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    progress_text.text(f"🔍 搜尋中...")
    
    articles = search_massive_news(keyword, limit=5)
    
    if not articles:
        st.warning(f"找不到 {keyword.upper()} 的新聞。")
        progress_bar.empty()
    else:
        results_data = []
        total = len(articles)
        
        # --- 平行處理 (Parallel Processing) ---
        # 這會同時開啟 5 個執行緒去下載、摘要、翻譯，速度提升 5 倍
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 提交任務
            future_to_article = {executor.submit(extract_and_process, item): item for item in articles}
            
            completed_count = 0
            for future in as_completed(future_to_article):
                result = future.result()
                if result:
                    results_data.append(result)
                
                completed_count += 1
                progress_text.text(f"正在處理 ({completed_count}/{total})...")
                progress_bar.progress(completed_count / total)
        
        # 排序回原本的時間順序 (因為平行處理完成順序不一定)
        # 簡單解法：這裡不特別排，因為差異不大，若要排可依時間欄位 sort
        
        progress_bar.empty()
        progress_text.empty()
        
        if results_data:
            st.success(f"✅ 完成！(含自動翻譯)")
            df = pd.DataFrame(results_data)
            st.dataframe(
                df, 
                column_config={
                    "連結": st.column_config.LinkColumn("連結", display_text="🔗 閱讀"),
                    "AI 重點摘要": st.column_config.TextColumn("AI 重點摘要", width="large")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("雖有找到新聞標題，但內容抓取失敗 (可能是付費牆或阻擋)。")
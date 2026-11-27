import os
import re
from datetime import datetime
import pandas as pd
import streamlit as st
from openai import OpenAI
from supabase import create_client, Client

# --- НАСТРОЙКА СТРАНИЦЫ ---
st.set_page_config(
    page_title="Тренажер ОТС (Глиц/Лаваль)",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- СОВРЕМЕННЫЙ ДИЗАЙН (АДАПТИВНЫЙ ПОД ТЁМНУЮ И СВЕТЛУЮ ТЕМЫ) ---
st.markdown("""
<style>
    .hero-card {
        background: linear-gradient(135deg, #0b3d91 0%, #1976d2 55%, #00acc1 100%);
        padding: 1.4rem 1.6rem;
        border-radius: 18px;
        color: white;
        margin-bottom: 1.1rem;
        box-shadow: 0 8px 24px rgba(11, 61, 145, 0.25);
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    .hero-card h1 {
        color: #ffffff !important;
        margin: 0;
        font-size: 1.65rem;
        font-weight: 700;
        letter-spacing: -0.3px;
    }
    .hero-card p {
        color: rgba(255, 255, 255, 0.9) !important;
        margin: 0.35rem 0 0 0;
        font-size: 0.95rem;
    }
    .badge {
        display: inline-block;
        background: rgba(255, 255, 255, 0.2);
        padding: 0.2rem 0.65rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-top: 0.6rem;
        color: #ffffff !important;
    }
    .stButton > button {
        border-radius: 10px;
        font-weight: 600;
        border: 1px solid rgba(128, 128, 128, 0.2);
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- СЕКРЕТЫ ---
def get_secret(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

API_KEY = get_secret("OPENROUTER_API_KEY", "")
APP_PASSWORD = get_secret("APP_PASSWORD", "seltfar2026")
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "admin2026")
MODEL_NAME = get_secret("MODEL_NAME", "google/gemini-2.5-flash")
SUPABASE_URL = get_secret("SUPABASE_URL", "")
SUPABASE_KEY = get_secret("SUPABASE_KEY", "")
RESULTS_FILE = "results.csv"
TRANSCRIPT_SEPARATOR = "\n\n===TRANSCRIPT_START===\n"

@st.cache_resource
def init_supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            return create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception:
            return None
    return None

supabase: Client | None = init_supabase()

def find_drug_images(prefix: str) -> list:
    found = []
    for suffix in ("_box", "_banner", ""):
        for ext in ("jpg", "jpeg", "png", "JPG"):
            path = f"{prefix}{suffix}.{ext}"
            if os.path.exists(path):
                found.append(path)
                break
    return found

# --- СЦЕНАРИИ ---
SCENARIOS = {
    "Лаваль vs Волвит (Биотин / акне)": {
        "drug": "Лаваль (50 мкг биотина — суточная норма, без риска акне)",
        "competitor": "Волвит",
        "context": "На ситуационный вопрос про витамины для волос и ногтей отвечай, что рекомендуешь Волвит.",
        "reference": """
- S: Какие витаминные комплексы вы назначаете при выпадении волос и для укрепления ногтей? (Ответ врача: Волвит)
- Проблема: В 1 таблетке Волвита 5 мг биотина (превышение суточной нормы 30-100 мкг в 100 раз), что увеличивает риск акне и кистозных угрей.
- P: К каким последствиям может привести появление угрей и кистозных акне на лице? (Рубцы, пигментные пятна)
- I: Пациент пьёт витамины для красоты, а получает акне, рубцы, пигментацию, моральные переживания и доп. траты на лечение/косметолога.
- N: Рекомендовали бы препарат с суточной нормой биотина 50 мкг, который не вызывает акне и лишних трат?
"""
    },
    "Лаваль vs Доппельгерц (Кератин / аминокислоты)": {
        "drug": "Лаваль (содержит Метионин и Цистеин для синтеза кератина)",
        "competitor": "Доппельгерц",
        "context": "На ситуационный вопрос про витамины для волос и ногтей отвечай, что рекомендуешь Доппельгерц.",
        "reference": """
- S: Какие витаминные комплексы вы назначаете при выпадении волос и для укрепления ногтей? (Ответ врача: Доппельгерц)
- Проблема: Для синтеза кератина нужны Метионин и Цистеин, которых нет в Доппельгерце.
- P: К чему приведёт нехватка кератина в короткие сроки? (Проблема не решится, волосы продолжат выпадать)
- I: Как отсутствие эффекта скажется на психологическом состоянии и качестве жизни пациента? (Негативно)
- N: Рекомендовали бы препарат с Метионином и Цистеином для образования кератина и укрепления волос?
"""
    },
    "Лаваль vs Волвит (Краситель Е124 / аллергия)": {
        "drug": "Лаваль (без высокоаллергенных компонентов)",
        "competitor": "Волвит",
        "context": "На ситуационный вопрос про витамины для волос и ногтей отвечай, что рекомендуешь Волвит.",
        "reference": """
- S: Какие витаминные комплексы вы назначаете при выпадении волос и для укрепления ногтей? (Ответ врача: Волвит)
- Проблема: В составе есть понсо 4R (Е124), способный вызвать аллергию от зудящих высыпаний до отёка Квинке.
- P: Насколько безопасен такой препарат при длительном приёме и как это ограничивает терапию? (Риск аллергии снижает возможности терапии)
- I: Пациент получает аллергию и доп. противоаллергическую терапию — реакция на назначение будет однозначно отрицательной.
- N: Рекомендовали бы препарат без высокоаллергенных компонентов и риска аллергии?
"""
    },
    "Глиц vs Дюфалак (Вздутие и 24–48 часов)": {
        "drug": "Глиц (на основе глицерина, местно, мягкий предсказуемый эффект за 15 мин, без вздутия)",
        "competitor": "Дюфалак",
        "context": "На ситуационный вопрос про средства от запора отвечай, что рекомендуешь Дюфалак.",
        "reference": """
- S: Какие средства от запора вы рекомендуете? (Ответ врача: Дюфалак)
- Проблема: В первые дни вызывает вздутие и метеоризм, а слабительный эффект наступает только через 2-3 дня (24-48 часов).
- P: Какие последствия возможны от внезапного непредсказуемого акта дефекации на работе или в дороге? (Очень деликатная ситуация)
- I: Постоянное ожидание и зависимость от непредсказуемого эффекта отрицательно влияют на качество жизни пациента.
- N: Рекомендовали бы местный препарат на основе глицерина с предсказуемым эффектом за 15 минут без вздутия и газообразования?
"""
    },
    "Глиц vs Форлакс (Макрогол и 24–48 часов)": {
        "drug": "Глиц (на основе глицерина, местно, мягкий предсказуемый эффект за 15 мин, без вздутия)",
        "competitor": "Форлакс",
        "context": "На ситуационный вопрос про средства от запора отвечай, что рекомендуешь Форлакс.",
        "reference": """
- S: Какие средства от запора вы рекомендуете? (Ответ врача: Форлакс)
- Проблема: Содержит Макрогол, действие которого начинается через 24-48 часов — дополнительный стресс при хроническом запоре.
- P: Нужен ли пациенту стресс от непредсказуемой дефекации в течение 24-48 часов на работе или в дороге? (Очень деликатная ситуация)
- I: Постоянное ожидание и зависимость от непредсказуемого эффекта ухудшают качество жизни пациента.
- N: Рекомендовали бы местный препарат на основе глицерина с предсказуемым эффектом за 15 минут без вздутия?
"""
    }
}

# --- ФОРМАТИРОВАНИЕ ДИАЛОГА И РАБОТА С БАЗОЙ ---
def format_transcript(messages: list) -> str:
    lines = []
    for m in messages:
        if m["role"] == "user" and m["content"].strip().upper() == "РАЗБОР":
            break
        role_label = "🧑‍💼 **Сотрудник:**" if m["role"] == "user" else "👩‍⚕️ **Асель Аскаровна:**"
        lines.append(f"{role_label} {m['content']}")
    return "\n\n".join(lines)

def split_feedback_and_transcript(raw_text: str):
    if not isinstance(raw_text, str):
        return "", ""
    if TRANSCRIPT_SEPARATOR in raw_text:
        feedback_part, transcript_part = raw_text.split(TRANSCRIPT_SEPARATOR, 1)
        return feedback_part.strip(), transcript_part.strip()
    return raw_text.strip(), ""

def save_result(employee_name: str, scenario_name: str, score: str, feedback: str, transcript: str):
    combined_payload = f"{feedback}{TRANSCRIPT_SEPARATOR}{transcript}"
    if supabase:
        try:
            supabase.table("spin_results").insert({
                "employee_name": employee_name,
                "scenario": scenario_name,
                "score": score,
                "feedback": combined_payload
            }).execute()
            return
        except Exception as e:
            st.warning(f"Ошибка записи в Supabase ({e}), сохраняю локально.")

    new_row = pd.DataFrame([{
        "Дата и время": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Сотрудник": employee_name,
        "Сценарий": scenario_name,
        "Оценка": score,
        "Разбор": combined_payload
    }])
    if os.path.exists(RESULTS_FILE):
        df = pd.read_csv(RESULTS_FILE)
        df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = new_row
    df.to_csv(RESULTS_FILE, index=False)

def load_results():
    cols = ["ID", "Дата и время", "Сотрудник", "Сценарий", "Оценка", "Разбор"]
    if supabase:
        try:
            res = supabase.table("spin_results").select("*").order("created_at", desc=True).execute()
            if res.data:
                df = pd.DataFrame(res.data)
                df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
                return df.rename(columns={
                    "id": "ID",
                    "created_at": "Дата и время",
                    "employee_name": "Сотрудник",
                    "scenario": "Сценарий",
                    "score": "Оценка",
                    "feedback": "Разбор"
                })[cols]
            return pd.DataFrame(columns=cols)
        except Exception:
            pass

    if os.path.exists(RESULTS_FILE):
        df = pd.read_csv(RESULTS_FILE)
        df.insert(0, "ID", df.index)
        return df[cols]
    return pd.DataFrame(columns=cols)

def delete_single_result(row_id):
    if supabase:
        try:
            supabase.table("spin_results").delete().eq("id", int(row_id)).execute()
            return True
        except Exception as e:
            st.error(f"Не удалось удалить из Supabase: {e}")
            return False
    elif os.path.exists(RESULTS_FILE):
        df = pd.read_csv(RESULTS_FILE)
        if row_id in df.index:
            df = df.drop(index=row_id).reset_index(drop=True)
            df.to_csv(RESULTS_FILE, index=False)
            return True
    return False

def extract_score(text: str) -> str:
    match = re.search(r"ИТОГОВАЯ ОЦЕНКА:\s*(\d+(?:[.,]\d+)?\s*/\s*10)", text, re.IGNORECASE)
    if match:
        return match.group(1).replace(" ", "")
    match_fallback = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*10", text)
    return f"{match_fallback.group(1)}/10" if match_fallback else "Нет оценки"

# --- ЭКРАН ВХОДА ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "admin_mode" not in st.session_state:
    st.session_state.admin_mode = False

if not st.session_state.authenticated:
    st.markdown("""
    <div class="hero-card">
        <h1>💊 Тренажер ОТС (Глиц/Лаваль)</h1>
        <p>Интерактивный симулятор визитов к врачу • Глиц и Лаваль</p>
        <span class="badge">Seltfar LTD • AI Training</span>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        st.subheader("🔐 Вход в систему")
        emp_name = st.text_input("Ваше ФИО", placeholder="Например: Иванов Иван")
        password = st.text_input("Пароль доступа", type="password")
        submit = st.form_submit_button("Начать тренировку", use_container_width=True, type="primary")

        if submit:
            if not emp_name.strip():
                st.error("Введите ваше ФИО, чтобы результаты сохранялись!")
            elif password == APP_PASSWORD:
                st.session_state.authenticated = True
                st.session_state.employee_name = emp_name.strip()
                st.rerun()
            else:
                st.error("Неверный пароль доступа.")
    st.stop()

# --- БОКОВАЯ ПАНЕЛЬ: ПАРАМЕТРЫ ВИЗИТА + ВХОД В АДМИНКУ ---
with st.sidebar:
    st.header("📋 Параметры визита")
    scenario_name = st.selectbox("Выберите сценарий:", list(SCENARIOS.keys()))
    scenario = SCENARIOS[scenario_name]

    with st.container(border=True):
        st.markdown(f"**Препарат:** {scenario['drug']}")
        st.markdown(f"**Конкурент:** `{scenario['competitor']}`")

        prefix = "laval" if "Лаваль" in scenario_name else "glitz"
        imgs = find_drug_images(prefix)
        for img in imgs:
            st.image(img, use_container_width=True)

    if st.button("🔄 Начать диалог заново", use_container_width=True):
        st.session_state.messages = []
        st.session_state.admin_mode = False
        st.rerun()

    st.divider()

    # --- КОМПАКТНЫЙ ВХОД В ПАНЕЛЬ РУКОВОДИТЕЛЯ ---
    with st.expander("🔒 Панель руководителя", expanded=st.session_state.admin_mode):
        db_status = "🟢 Supabase подключён" if supabase else "🟡 Локальный CSV"
        st.caption(db_status)

        if not st.session_state.admin_mode:
            admin_pass = st.text_input("Пароль админа", type="password", key="admin_pass_input")
            if st.button("Открыть на весь экран", use_container_width=True, type="primary"):
                if admin_pass == ADMIN_PASSWORD:
                    st.session_state.admin_mode = True
                    st.rerun()
                else:
                    st.error("Неверный пароль.")
        else:
            st.success("Режим руководителя активен")
            if st.button("⬅️ Вернуться в тренажёр", use_container_width=True):
                st.session_state.admin_mode = False
                st.rerun()

# =========================================================
# РЕЖИМ 1: ПОЛНОЭКРАННАЯ ПАНЕЛЬ РУКОВОДИТЕЛЯ
# =========================================================
if st.session_state.admin_mode:
    col_title, col_back = st.columns([4, 1])
    with col_title:
        st.markdown("""
        <div class="hero-card">
            <h1>📊 Панель руководителя</h1>
            <p>Результаты, переписки и разборы тренировок сотрудников</p>
        </div>
        """, unsafe_allow_html=True)
    with col_back:
        if st.button("⬅️ Назад к чату", use_container_width=True):
            st.session_state.admin_mode = False
            st.rerun()

    df = load_results()
    if df.empty:
        st.info("Пока нет сохранённых результатов. Когда сотрудники завершат тренировку, данные появятся здесь.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("Всего тренировок", len(df))
        m2.metric("Сотрудников", df["Сотрудник"].nunique())
        m3.metric("Сценариев пройдено", df["Сценарий"].nunique())

        st.divider()

        c_filter, c_dl = st.columns([2, 1])
        with c_filter:
            employees = ["Все сотрудники"] + sorted(df["Сотрудник"].unique().tolist())
            selected_emp = st.selectbox("Фильтр по сотруднику:", employees)
            filtered_df = df if selected_emp == "Все сотрудники" else df[df["Сотрудник"] == selected_emp]

        with c_dl:
            st.write("")
            st.write("")
            csv_data = filtered_df.drop(columns=["ID"]).to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="📥 Скачать Excel (CSV)",
                data=csv_data,
                file_name=f"spin_results_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
                type="primary"
            )

        st.dataframe(
            filtered_df[["Дата и время", "Сотрудник", "Сценарий", "Оценка"]],
            use_container_width=True,
            hide_index=True
        )

        st.subheader("📝 Переписки и разборы сотрудников")
        for _, row in filtered_df.iterrows():
            feedback_text, transcript_text = split_feedback_and_transcript(row["Разбор"])
            with st.expander(f"{row['Дата и время']} — {row['Сотрудник']} ({row['Оценка']}) • {row['Сценарий']}"):
                t_chat, t_eval = st.tabs(["💬 Переписка сотрудника", "📊 Разбор от ИИ"])
                with t_chat:
                    if transcript_text:
                        st.markdown(transcript_text)
                    else:
                        st.caption("Для этой старой записи переписка ещё не сохранялась.")
                with t_eval:
                    st.markdown(feedback_text)

                st.divider()
                if st.button("🗑️ Удалить эту запись", key=f"del_{row['ID']}"):
                    if delete_single_result(row["ID"]):
                        st.toast("Запись удалена!", icon="🗑️")
                        st.rerun()

    st.stop()

# =========================================================
# РЕЖИМ 2: ОСНОВНОЙ ЧАТ ТРЕНАЖЁРА
# =========================================================
st.markdown(f"""
<div class="hero-card">
    <h1>💊Тренажер ОТС (Глиц/Лаваль)</h1>
    <p>Сценарий: <b>{scenario_name}</b></p>
    <span class="badge">🧑‍💼 {st.session_state.employee_name}</span>
</div>
""", unsafe_allow_html=True)

# --- ЭКРАНЧИК / ДОСЬЕ ВРАЧА ---
with st.container(border=True):
    st.markdown("#### 👩‍⚕️ Карточка врача: Асель Аскаровна")
    st.markdown(
        f"**Специальность:** Врач-терапевт на приёме в поликлинике  \n"
        f"**Характер:** Занятая, скептичная, не любит шаблонное «впаривание» в лоб. Ценит чёткие факты и заботу о пациентах.  \n"
        f"**Текущее назначение:** Обычно рекомендует **{scenario['competitor']}**.  \n"
        f"**Ваша задача:** Провести визит по технике **SPIN** (Ситуационный → Проблемный → Извлекающий → Направляющий) и подвести врача к назначению нашего препарата."
    )

SYSTEM_PROMPT = f"""
СТРОГОЕ РАСПРЕДЕЛЕНИЕ РОЛЕЙ (НЕ ПУТАТЬ!):
- ТЫ (ассистент) — ТОЛЬКО врач-терапевт Асель Аскаровна на приёме в поликлинике.
- ПОЛЬЗОВАТЕЛЬ — медицинский представитель компании Seltfar (Сэлтфар), который пришёл к тебе продвигать препарат: {scenario['drug']}.

ЖЕЛЕЗНЫЕ ПРАВИЛА ПОВЕДЕНИЯ ВРАЧА:
1. НИКОГДА не говори от лица медпреда, не задавай SPIN-вопросы вместо пользователя и не называй пользователя «Асель Аскаровна» (Асель Аскаровна — это ТЫ!).
2. Если пользователь написал непонятное слово, опечатку или набор букв (типа «Воочо» или «ывфа»), оставайся в роли врача и переспроси: «Простите, я не совсем поняла, вы ко мне по какому вопросу? У меня скоро следующий пациент».
3. {scenario['context']}
4. Отвечай коротко и естественно (1–3 предложения), как занятой врач на приёме.
5. Не подсказывай медпреду сам. Соглашайся с доводами и раскрывай последствия, только если медпред грамотно ведёт тебя по воронке SPIN.
6. Если медпред начинает продавать препарат в лоб, минуя проблемы конкурента ({scenario['competitor']}), отвечай скептически.

Эталонный скрипт SPIN (используй ТОЛЬКО для понимания логики и финальной оценки, НЕ озвучивай реплики медпреда из него!):
{scenario['reference']}

Если пользователь пишет «РАЗБОР» — выйди из роли врача и дай чёткий разбор диалога по эталонному скрипту выше:
- Оцени этапы: S (Ситуационный), Проблема конкурента, P (Проблемный), I (Извлекающий/усугубляющий), N (Выгодность решения).
- Укажи, какие аргументы из эталона медпред упустил.
- В самом конце ОБЯЗАТЕЛЬНО напиши строку строго в формате:
ИТОГОВАЯ ОЦЕНКА: X/10
"""

if st.session_state.get("current_scenario") != scenario_name:
    st.session_state.current_scenario = scenario_name
    st.session_state.messages = []

if "messages" not in st.session_state:
    st.session_state.messages = []

if not st.session_state.messages:
    st.info("👋 Поздоровайтесь с Асель Аскаровной и задайте первый ситуационный вопрос.")

for msg in st.session_state.messages:
    avatar = "🧑‍💼" if msg["role"] == "user" else "👩‍⚕️"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# --- КНОПКА ЗАВЕРШЕНИЯ ПРЯМО В ЧАТЕ ---
evaluate_clicked = False
if st.session_state.messages:
    st.write("")
    evaluate_clicked = st.button(
        "📊 Завершить визит и сохранить результат",
        use_container_width=True,
        type="primary"
    )

user_input = st.chat_input("Напишите реплику Асель Аскаровне...")
is_evaluation = False

if evaluate_clicked:
    user_input = "РАЗБОР"
    is_evaluation = True

if user_input:
    if user_input.strip().upper() == "РАЗБОР":
        is_evaluation = True

    if not API_KEY:
        st.error("Ошибка: не задан OPENROUTER_API_KEY в Streamlit Secrets!")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(user_input)

    client = OpenAI(api_key=API_KEY, base_url="https://openrouter.ai/api/v1")

    with st.chat_message("assistant", avatar="👩‍⚕️"):
        with st.spinner("Асель Аскаровна отвечает..." if not is_evaluation else "Формирую разбор и сохраняю в базу..."):
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + st.session_state.messages,
                temperature=0.6
            )
            reply = response.choices[0].message.content
            st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})

    if is_evaluation:
        score = extract_score(reply)
        transcript = format_transcript(st.session_state.messages)
        save_result(st.session_state.employee_name, scenario_name, score, reply, transcript)
        st.toast(f"Результат ({score}) и переписка сохранены!", icon="✅")

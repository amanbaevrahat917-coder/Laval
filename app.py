import os
import re
from datetime import datetime
import pandas as pd
import streamlit as st
from openai import OpenAI

# --- НАСТРОЙКА СТРАНИЦЫ ---
st.set_page_config(
    page_title="Seltfar SPIN-Тренажёр",
    page_icon="💊",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- КАСТОМНЫЙ ДИЗАЙН (БЕЗ СЛОМАННОГО ФОНА) ---
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #0f4c81 0%, #1e88e5 100%);
        padding: 1.4rem;
        border-radius: 16px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 15px rgba(15, 76, 129, 0.2);
    }
    .main-header h1 {
        color: white !important;
        margin: 0;
        font-size: 1.7rem;
    }
    .main-header p {
        color: #e3f2fd !important;
        margin: 0.3rem 0 0 0;
        font-size: 0.95rem;
    }
    .stButton > button {
        border-radius: 10px;
        font-weight: 600;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- СЕКРЕТЫ И ПАРОЛИ ---
def get_secret(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

API_KEY = get_secret("OPENROUTER_API_KEY", "")
APP_PASSWORD = get_secret("APP_PASSWORD", "seltfar2026")
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD", "admin2026")
MODEL_NAME = get_secret("MODEL_NAME", "google/gemini-2.5-flash")
RESULTS_FILE = "results.csv"

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

# --- БАЗА РЕЗУЛЬТАТОВ ---
def save_result(employee_name: str, scenario_name: str, score: str, feedback: str):
    new_row = pd.DataFrame([{
        "Дата и время": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "Сотрудник": employee_name,
        "Сценарий": scenario_name,
        "Оценка": score,
        "Разбор": feedback
    }])
    if os.path.exists(RESULTS_FILE):
        df = pd.read_csv(RESULTS_FILE)
        df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = new_row
    df.to_csv(RESULTS_FILE, index=False)

def load_results():
    if os.path.exists(RESULTS_FILE):
        return pd.read_csv(RESULTS_FILE)
    return pd.DataFrame(columns=["Дата и время", "Сотрудник", "Сценарий", "Оценка", "Разбор"])

def extract_score(text: str) -> str:
    match = re.search(r"ИТОГОВАЯ ОЦЕНКА:\s*(\d+(?:[.,]\d+)?\s*/\s*10)", text, re.IGNORECASE)
    if match:
        return match.group(1).replace(" ", "")
    match_fallback = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*10", text)
    return f"{match_fallback.group(1)}/10" if match_fallback else "Нет оценки"

# --- ЭКРАН ВХОДА ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("""
    <div class="main-header">
        <h1>💊 SPIN-Тренажёр Медпреда</h1>
        <p>Интерактивный симулятор визитов к врачу • Глиц и Лаваль</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        st.subheader("🔐 Вход в систему")
        emp_name = st.text_input("Ваше ФИО", placeholder="Например: Иванов Иван")
        password = st.text_input("Пароль доступа", type="password")
        submit = st.form_submit_button("Войти", use_container_width=True, type="primary")

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

# --- БОКОВАЯ ПАНЕЛЬ: ПАРАМЕТРЫ ВИЗИТА + АДМИНКА ---
with st.sidebar:
    st.header("📋 Параметры визита")
    scenario_name = st.selectbox("Выберите сценарий:", list(SCENARIOS.keys()))
    scenario = SCENARIOS[scenario_name]

    st.info(f"**Препарат:** {scenario['drug']}\n\n**Конкурент:** {scenario['competitor']}")

    if st.button("🔄 Начать диалог заново", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    evaluate_clicked = st.button(
        "📊 Завершить и сохранить результат",
        use_container_width=True,
        type="primary"
    )

    st.divider()

    # --- ПАНЕЛЬ РУКОВОДИТЕЛЯ ПРЯМО В САЙДБАРЕ ---
    with st.expander("🔒 Панель руководителя"):
        admin_pass = st.text_input("Пароль админа", type="password", key="admin_pass_input")

        if admin_pass == ADMIN_PASSWORD:
            df = load_results()
            if df.empty:
                st.info("Пока нет сохранённых результатов.")
            else:
                st.metric("Всего тренировок", len(df))
                st.metric("Сотрудников", df["Сотрудник"].nunique())

                employees = ["Все"] + sorted(df["Сотрудник"].unique().tolist())
                selected_emp = st.selectbox("Сотрудник:", employees)
                filtered_df = df if selected_emp == "Все" else df[df["Сотрудник"] == selected_emp]

                st.dataframe(
                    filtered_df[["Дата и время", "Сотрудник", "Оценка"]],
                    use_container_width=True,
                    hide_index=True
                )

                csv_data = filtered_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 Скачать отчёт (Excel/CSV)",
                    data=csv_data,
                    file_name=f"spin_results_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    type="primary"
                )

                if st.button("🗑️ Очистить базу", use_container_width=True):
                    if os.path.exists(RESULTS_FILE):
                        os.remove(RESULTS_FILE)
                    st.rerun()
        elif admin_pass:
            st.error("Неверный пароль.")

# --- ОСНОВНОЙ ЧАТ ---
st.markdown(f"""
<div class="main-header">
    <h1>💊 SPIN-Тренажёр: Глиц и Лаваль</h1>
    <p>Сотрудник: <b>{st.session_state.employee_name}</b></p>
</div>
""", unsafe_allow_html=True)

SYSTEM_PROMPT = f"""
Ты — врач Асель Аскаровна на приёме. К тебе пришёл медпредставитель с препаратом: {scenario['drug']}.
Твоё поведение в роли врача:
1. {scenario['context']}
2. Отвечай естественно и коротко (1-3 предложения), как занятой врач на приёме.
3. Не подсказывай медпреду сам. Соглашайся с доводами и раскрывай последствия, только если медпред грамотно ведёт по воронке SPIN.
4. Если медпред начинает продавать препарат в лоб, минуя проблемы конкурента ({scenario['competitor']}), отвечай скептически.

Эталонный скрипт SPIN для этого сценария:
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
    st.caption("👋 Начните диалог с Асель Аскаровной — поздоровайтесь и задайте первый ситуационный вопрос.")

for msg in st.session_state.messages:
    avatar = "🧑‍💼" if msg["role"] == "user" else "👩‍⚕️"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

user_input = st.chat_input("Напишите реплику врачу...")
is_evaluation = False

if evaluate_clicked:
    if not st.session_state.messages:
        st.warning("Сначала проведите хотя бы небольшой диалог с врачом!")
    else:
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
        with st.spinner("Асель Аскаровна думает..." if not is_evaluation else "Формирую разбор и сохраняю результат..."):
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
        save_result(st.session_state.employee_name, scenario_name, score, reply)
        st.toast(f"Результат ({score}) сохранён!", icon="✅")

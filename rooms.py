import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- 1. הגדרות וחיבורים (נמשך מה-Secrets של Streamlit) ---
SOURCE_URL = st.secrets.get('SOURCE_URL') or st.secrets.get('SUPABASE_URL')
SOURCE_KEY = st.secrets.get('SOURCE_KEY') or st.secrets.get('SUPABASE_KEY')
MY_URL = st.secrets.get('MY_URL')
MY_KEY = st.secrets.get('MY_KEY')
REFRESH_TOKEN = st.secrets.get('REFRESH_TOKEN', '')

# הגדרת אזור זמן ישראל
IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now():
    """פונקציה שמחזירה תמיד את השעה המדויקת בישראל"""
    return datetime.now(IL_TZ)

def format_simple_clock(total_seconds):
    """מציגה שעון בפורמט HH:MM:SS נקי ובולט"""
    total_seconds = int(total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"## **{hours:02d}:{minutes:02d}:{seconds:02d}**"

# --- 2. פונקציות תקשורת ---
def get_source_headers():
    """משיגת אישור כניסה למערכת ההזמנות המקורית"""
    auth_url = f"{SOURCE_URL}/auth/v1/token?grant_type=refresh_token"
    try:
        res = requests.post(auth_url, json={"refresh_token": REFRESH_TOKEN}, headers={"apikey": SOURCE_KEY}, timeout=5)
        if res.status_code == 200:
            token = res.json().get("access_token")
            return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {token}"}
    except:
        pass
    return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {SOURCE_KEY}"}

def get_my_headers():
    """אישור כניסה למסד הנתונים הפרטי שלך"""
    return {"apikey": MY_KEY, "Authorization": f"Bearer {MY_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}

def send_telegram(msg):
    """שולחת הודעה לבוט הטלגרם שלך"""
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try: requests.get(url, params={"chat_id": chat_id, "text": msg}, timeout=5)
        except: pass

def calculate_price_logic(total_p, paying_p, elapsed_m):
    """הלוגיקה המדויקת של תמחור הקריוקי שלך"""
    if total_p == 1: rates = [50, 40, 30]
    elif 2 <= total_p <= 4: rates = [45, 35, 25]
    elif 5 <= total_p <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]
    
    if elapsed_m <= 120: p = (elapsed_m / 60) * rates[0]
    elif elapsed_m <= 180: p = (120/60 * rates[0]) + ((elapsed_m - 120) / 60 * rates[1])
    else: p = (120/60 * rates[0]) + (60/60 * rates[1]) + ((elapsed_m - 180) / 60 * rates[2])
    
    total = p * total_p
    per = total / paying_p if paying_p > 0 else 0
    return total, per

def sync_data():
    """חיפוש עמוק של הזמנות כדי למנוע מצב של רשימה ריקה"""
    headers = get_source_headers()
    # מושך את 100 ההזמנות האחרונות שנוצרו (ללא פילטר תאריך קשיח בשרת)
    params = {"select": "*,room:rooms(*)", "order": "created_at.desc", "limit": "100"}
    res = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=headers, params=params, timeout=10)
    
    if res.status_code != 200:
        st.error(f"שגיאת תקשורת עם המקור: {res.status_code}")
        return []
    return res.json()

# --- 3. ממשק משתמש (UI) ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זהבי")

# תפריט צד לאיפוס במקרה הצורך
with st.sidebar:
    if st.button("🗑️ איפוס נתונים"):
        st.session_state.clear()
        st.rerun()

# בחירת תאריך לתצוגה
view_date = st.date_input("📅 הצג הזמנות ליום:", get_now().date())
selected_str = view_date.strftime("%Y-%m-%d")

if st.button("🔄 סנכרן נתונים מהענן", use_container_width=True):
    with st.spinner("סורק הזמנות..."):
        st.session_state.raw_data = sync_data()
        if st.session_state.raw_data:
            st.success(f"הסנכרון הצליח! נסרקו 100 פעולות אחרונות.")
        else:
            st.warning("לא נמצאו נתונים. וודאי שהמפתחות ב-Secrets נכונים.")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון מחיר"])

# --- טאב 1: לוח הזמנות ---
with tab1:
    if 'raw_data' in st.session_state:
        # סינון מקומי לפי התאריך שנבחר
        day_bookings = []
        for b in st.session_state.raw_data:
            # בודק תאריך בכמה שדות אפשריים (גמישות מירבית)
            b_date = b.get('booking_date') or b.get('date') or (b.get('start_time')[:10] if b.get('start_time') else None)
            if b_date == selected_str and b.get('status') != 'cancelled':
                day_bookings.append(b)
        
        if day_bookings:
            # בודק מי כבר נכנס לחדר
            res_a = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
            active_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
            
            for b in day_bookings:
                bid = str(b['id'])
                if bid in active_ids: continue
                
                name = b.get('customer_name') or b.get('name') or 'לקוח'
                start_raw = b.get('start_time', '--:--')
                start_display = start_raw.split('T')[1][:5] if 'T' in start_raw else start_raw[:5]
                dur = b.get('duration_minutes') or 60
                people = b.get('total_people') or 2
                
                with st.expander(f"⏳ {name} | {start_display} ({dur} דק')"):
                    p_in = st.number_input("כמות אנשים", 1, 50, int(people), key=f"p_{bid}")
                    d_in = st.number_input("זמן מוזמן (דק')", 15, 300, int(dur), key=f"d_{bid}")
                    r_orig = b.get('room', {}).get('name') or 'חדר'
                    r_act = st.text_input("חדר בפועל", value=r_orig, key=f"r_{bid}")
                    
                    if st.button("🚀 כניסה לחדר", key=f"in_{bid}", use_container_width=True):
                        payload = {
                            "booking_id": bid, "name": name, "room_name": r_act,
                            "start_time": get_now().isoformat(), "total_people": p_in,
                            "paying_people": p_in, "planned_duration": d_in, "status": "active"
                        }
                        res = requests.post(f"{MY_URL}/rest/v1/active_sessions", json=payload, headers=get_my_headers())
                        if res.status_code in [200, 201]:
                            send_telegram(f"✅ כניסה: {name} ל-{r_act} ({p_in} איש, {d_in} דק')")
                            st.rerun()
        else:
            st.info(f"לא נמצאו הזמנות ליום {selected_str}. נסי להחליף תאריך או לסנכרן שוב.")
    else:
        st.info("לחצי על כפתור הסנכרון למעלה כדי לטעון הזמנות.")

# --- טאב 2: חדרים בפעילות ---
with tab2:
    v_filter = st.radio("תצוגה:", ["⚡ פעילים עכשיו", "🏁 סיימו"], horizontal=True)
    
    @st.fragment(run_every=5)
    def active_sessions_timer():
        res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res.status_code == 200:
            rooms = res.json()
            # סינון לפי סטטוס ותאריך
            disp = [r for r in rooms if r.get('status', 'active').startswith('active')] if v_filter == "⚡ פעילים עכשיו" else [r for r in rooms if r.get('status') == 'finished']
            
            # הצגת החדרים
            count = 0
            for r in disp:
                s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                if s_dt.date() != view_date: continue
                
                count += 1
                planned = r.get('planned_duration', 60)
                if r.get('status').startswith('active'):
                    diff = get_now() - s_dt
                    st.subheader(f"📍 {r['room_name']} | {r['name']} (הוזמן ל-{planned} דק')")
                    
                    pay_p = st.number_input("משלמים", 1, 50, r['paying_people'], key=f"pay_{r['id']}")
                    total_p = r['total_people']
                    total_cost, per_person = calculate_price_logic(total_p, pay_p, diff.total_seconds()/60)
                    
                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1:
                        st.write("⏱️ **זמן שחלף:**")
                        st.write(format_simple_clock(diff.total_seconds()))
                    c2.metric("💰 סה\"כ", f"₪{total_cost:.2f}")
                    c3.metric("👤 לאדם", f"₪{per_person:.2f}")
                    
                    if st.button(f"💰 סיום ותשלום ל-{r['name']}", key=f"end_{r['id']}", use_container_width=True):
                        requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", 
                                       json={"status":"finished", "end_time":get_now().isoformat(), "paying_people": pay_p}, headers=get_my_headers())
                        send_telegram(f"💸 סיום: {r['name']} יצאו מ-{r['room_name']}. נגבה: ₪{total_cost:.2f}")
                        st.rerun()
                else:
                    # חדרים שסיימו
                    e_dt = datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                    diff = e_dt - s_dt
                    total_cost, _ = calculate_price_logic(r['total_people'], r['paying_people'], diff.total_seconds()/60)
                    st.success(f"🏁 {r['room_name']} | {r['name']} - סיימו ב-{e_dt.strftime('%H:%M')} (סה\"כ ₪{total_cost:.2f})")
                st.divider()
            
            if count == 0:
                st.info("אין חדרים להצגה ליום זה.")

    active_sessions_timer()

# --- טאב 3: מחשבון מחיר ---
with tab3:
    st.subheader("🧮 מחשבון מחיר מהיר")
    c_name = st.text_input("שם הלקוח", "לקוח כללי")
    col1, col2, col3 = st.columns(3)
    c_total = col1.number_input("סה\"כ אנשים", 1, 50, 4)
    c_pay = col2.number_input("משלמים בפועל", 1, 50, 4)
    c_mins = col3.number_input("זמן (דקות)", 1, 600, 60)
    
    total_res, per_res = calculate_price_logic(c_total, c_pay, c_mins)
    
    st.divider()
    res_col1, res_col2 = st.columns(2)
    res_col1.metric("💰 סה\"כ לתשלום", f"₪{total_res:.2f}")
    res_col2.metric("👤 מחיר לאדם", f"₪{per_res:.2f}")
    
    if st.button("📤 שלח תוצאה לטלגרם", use_container_width=True):
        send_telegram(f"📝 בדיקת מחיר ל-{c_name}:\n⏱️ זמן: {c_mins} דק'\n👥 סה\"כ: {c_total} איש\n💵 סה\"כ: ₪{total_res:.2f}\n👤 לאדם: ₪{per_res:.2f}")
        st.success("נשלח!")

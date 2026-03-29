import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time

# --- הגדרות חיבור ---
SOURCE_URL = st.secrets['SUPABASE_URL']
SOURCE_KEY = st.secrets['SUPABASE_KEY']
MY_URL = st.secrets['MY_URL']
MY_KEY = st.secrets['MY_KEY']
IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now():
    return datetime.now(IL_TZ)

def format_duration_vertical(total_seconds):
    """מחזירה מחרוזת מעוצבת אנכית ברורה ובלטת"""
    total_mins = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    
    if total_mins >= 60:
        h = total_mins // 60
        m = total_mins % 60
        # פורמט אנכי: בולד בולט, ופירוט מלא בשורה מתחתיו
        return f"## **{h:02d}:{m:02d}:{seconds:02d}** \n\n ({h} שע', {m} דק', {seconds} שנ')"
    else:
        return f"## **{total_mins:02d}:{seconds:02d}** \n\n ({total_mins} דק', {seconds} שנ')"

# --- פונקציות ליבה ---
def get_source_headers():
    auth_url = f"{SOURCE_URL}/auth/v1/token?grant_type=refresh_token"
    res = requests.post(auth_url, json={"refresh_token": st.secrets["REFRESH_TOKEN"]}, headers={"apikey": SOURCE_KEY})
    token = res.json().get("access_token")
    return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {token}"}

def get_my_headers():
    return {"apikey": MY_KEY, "Authorization": f"Bearer {MY_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}

def send_telegram(msg):
    token = st.secrets.get("TELEGRAM_TOKEN")
    chat_id = st.secrets.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try: requests.get(url, params={"chat_id": chat_id, "text": msg})
        except: pass

def calculate_price_logic(total_p, paying_p, elapsed_m):
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

def sync_and_cleanup(selected_date):
    now = get_now()
    q_date = (now - timedelta(days=1)).strftime("%Y-%m-%d") if (selected_date == now.date() and now.hour < 6) else selected_date.strftime("%Y-%m-%d")
    is_current = (q_date == now.strftime("%Y-%m-%d")) or (now.hour < 6 and q_date == (now - timedelta(days=1)).strftime("%Y-%m-%d"))
    res = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=get_source_headers(), params={"booking_date": f"eq.{q_date}", "status": "neq.cancelled", "select": "*,room:rooms(*)"})
    if res.status_code != 200: return []
    source_bookings = res.json()
    if is_current:
        ids = [str(b['id']) for b in source_bookings]
        my_res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if my_res.status_code == 200:
            for r in my_res.json():
                if str(r['booking_id']) not in ids and r.get('status', 'active').startswith('active'):
                    requests.delete(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", headers=get_my_headers())
    return source_bookings

def get_shift_date(iso):
    if not iso: return None
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(IL_TZ)
        return (dt - timedelta(days=1)).date() if dt.hour < 6 else dt.date()
    except: return None

# --- ממשק ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זיכרון קבוע")

selected_date = st.date_input("📅 בחר תאריך להצגה", get_now().date())
if st.button("🔄 סנכרן נתונים", use_container_width=True):
    st.session_state.web_bookings = sync_and_cleanup(selected_date)
    st.success("עודכן!")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ חדרים בפעילות", "🧮 מחשבון"])

with tab1:
    if 'web_bookings' in st.session_state:
        res_a = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        a_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
        for b in st.session_state.web_bookings:
            bid = str(b['id'])
            if bid in a_ids: continue
            with st.expander(f"⏳ {b.get('customer_name')} | {b.get('start_time')} | {b.get('room',{}).get('name')}"):
                p = st.number_input("אנשים", 1, 50, 2, key=f"p_{bid}")
                d = st.number_input("דקות", 15, 300, 60, key=f"d_{bid}")
                r_act = st.text_input("חדר", value=b.get('room',{}).get('name'), key=f"r_{bid}")
                if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                    requests.post(f"{MY_URL}/rest/v1/active_sessions", json={"booking_id":bid,"name":b.get('customer_name'),"room_name":r_act,"start_time":get_now().isoformat(),"total_people":p,"paying_people":p,"planned_duration":d,"status":"active"}, headers=get_my_headers())
                    send_telegram(f"✅ כניסה: {b.get('customer_name')} ל-{r_act} ({p} איש, {d} דק')")
                    st.rerun()

with tab2:
    v = st.radio("תצוגה:", ["⚡ עכשיו בפעילות", "🏁 סיימו"], horizontal=True)
    @st.fragment(run_every=5)
    def timer():
        res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        rooms = [r for r in (res.json() if res.status_code==200 else []) if get_shift_date(r['start_time']) == selected_date]
        disp = [r for r in rooms if r.get('status','active').startswith('active')] if v == "⚡ עכשיו בפעילות" else [r for r in rooms if r.get('status') == 'finished']
        
        for r in disp:
            s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
            if r.get('status') == 'finished':
                e_dt = datetime.fromisoformat(r['end_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                diff = e_dt - s_dt
                active = False
            else:
                diff = get_now() - s_dt
                active = True
            
            st.subheader(f"📍 {r['room_name']} | {r['name']} (נכנסו ב-{s_dt.strftime('%H:%M')})")
            
            if active:
                pay = st.number_input("مشלמים", 1, 50, r['paying_people'], key=f"pay_{r['id']}")
                total, per = calculate_price_logic(r['total_people'], pay, diff.total_seconds()/60)
                
                c1, c2, c3 = st.columns([2, 1, 1]) # נותן לעמודה של הזמן קצת יותר רוחב
                
                # --- תצוגה אנכית ומסודרת ---
                with c1:
                    st.write("⏱️ **זמן:**")
                    st.write(format_duration_vertical(diff.total_seconds()))
                    
                c2.metric("💰 **סה\"כ**", f"₪{total:.2f}")
                c3.metric("👤 **לאדם**", f"₪{per:.2f}")
                
                if st.button(f"💰 סיום ל-{r['name']}", key=f"e_{r['id']}", use_container_width=True):
                    requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished","end_time":get_now().isoformat(),"paying_people":pay}, headers=get_my_headers())
                    send_telegram(f"💸 סיום: {r['name']} סיימו. נגבה ₪{total:.2f}")
                    st.rerun()
            else:
                total, per = calculate_price_logic(r['total_people'], r['paying_people'], diff.total_seconds()/60)
                st.success(f"הסתיים. נגבה: ₪{total:.2f}")
            st.divider()
    timer()

with tab3:
    st.subheader("🧮 מחשבון")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("סה\"כ איש", 1, 50, 4), c2.number_input("משלמים", 1, 50, 4), c3.number_input("דקות", 1, 600, 60)
    t, p = calculate_price_logic(c_tot, c_pay, c_min)
    st.metric("סה\"כ", f"₪{t:.2f}")
    if st.button("📤 שלח לטלגרם"):
        send_telegram(f"📝 מחשבון: {c_min} דק', {c_tot} איש. סה\"כ: ₪{t:.2f}")

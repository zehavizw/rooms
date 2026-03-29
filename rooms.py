import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- הגדרות חיבור ---
SOURCE_URL = st.secrets.get('SOURCE_URL') or st.secrets.get('SUPABASE_URL')
SOURCE_KEY = st.secrets.get('SOURCE_KEY') or st.secrets.get('SUPABASE_KEY')
MY_URL = st.secrets.get('MY_URL')
MY_KEY = st.secrets['MY_KEY']
REFRESH_TOKEN = st.secrets.get('REFRESH_TOKEN', '')

IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now():
    return datetime.now(IL_TZ)

# --- פונקציות ליבה ---
def get_source_headers():
    auth_url = f"{SOURCE_URL}/auth/v1/token?grant_type=refresh_token"
    try:
        res = requests.post(auth_url, json={"refresh_token": REFRESH_TOKEN}, headers={"apikey": SOURCE_KEY}, timeout=5)
        if res.status_code == 200:
            token = res.json().get("access_token")
            return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {token}"}
    except: pass
    return {"apikey": SOURCE_KEY, "Authorization": f"Bearer {SOURCE_KEY}"}

def get_my_headers():
    return {"apikey": MY_KEY, "Authorization": f"Bearer {MY_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}

def sync_all_upcoming():
    """מושך את כל ההזמנות מהשבוע האחרון ועד שבוע קדימה כדי למנוע פספוסים"""
    today = get_now().date()
    start_search = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    end_search = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    
    headers = get_source_headers()
    # חיפוש לפי טווח תאריכים במקום תאריך בודד
    params = {
        "booking_date": f"gte.{start_search}",
        "booking_date": f"lte.{end_search}",
        "select": "*,room:rooms(*)",
        "order": "booking_date.asc,start_time.asc"
    }
    
    res = requests.get(f"{SOURCE_URL}/rest/v1/bookings", headers=headers, params=params, timeout=10)
    
    if res.status_code != 200:
        st.error(f"שגיאת תקשורת: {res.status_code}")
        return []
        
    return [b for b in res.json() if b.get('status') != 'cancelled']

# --- ממשק ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - זהבי")

with st.sidebar:
    if st.button("🗑️ איפוס מלא"):
        st.session_state.clear()
        st.rerun()

# בחירת תאריך להצגה באפליקציה
view_date = st.date_input("📅 הצג הזמנות ליום:", get_now().date())

if st.button("🔄 סנכרן נתונים", use_container_width=True):
    with st.spinner("מעדכן נתונים מהענן..."):
        st.session_state.all_bookings = sync_all_upcoming()
        st.success("הסנכרון הושלם!")

st.divider()
tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ עכשיו בפעילות", "🧮 מחשבון"])

with tab1:
    if 'all_bookings' in st.session_state:
        # סינון מקומי רק ליום שנבחר בלוח השנה
        selected_str = view_date.strftime("%Y-%m-%d")
        day_bookings = [b for b in st.session_state.all_bookings if b.get('booking_date') == selected_str]
        
        if day_bookings:
            # בדיקה מי כבר בחדר
            res_a = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
            active_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
            
            for b in day_bookings:
                bid = str(b['id'])
                if bid in active_ids: continue
                
                name = b.get('customer_name', 'לקוח')
                start = b.get('start_time', '--:--')
                dur = b.get('duration_minutes') or 60
                people = b.get('total_people') or 2
                
                with st.expander(f"⏳ {name} | {start} ({dur} דק')"):
                    p = st.number_input("אנשים", 1, 50, int(people), key=f"p_{bid}")
                    d = st.number_input("דקות", 15, 300, int(dur), key=f"d_{bid}")
                    r_name = b.get('room', {}).get('name', 'לא הוקצה')
                    r_act = st.text_input("חדר", value=r_name, key=f"r_{bid}")
                    
                    if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                        payload = {
                            "booking_id": bid, "name": name, "room_name": r_act,
                            "start_time": get_now().isoformat(), "total_people": p,
                            "paying_people": p, "planned_duration": d, "status": "active"
                        }
                        requests.post(f"{MY_URL}/rest/v1/active_sessions", json=payload, headers=get_my_headers())
                        st.rerun()
        else:
            st.warning(f"לא נמצאו הזמנות ליום {selected_str}. נסי להחליף תאריך או לסנכרן שוב.")
    else:
        st.info("לחצי על כפתור הסנכרון כדי לטעון הזמנות.")

# שאר הטאבים (פעילות ומחשבון) נשארים אותו דבר...
with tab2:
    @st.fragment(run_every=5)
    def active_timer():
        res = requests.get(f"{MY_URL}/rest/v1/active_sessions", headers=get_my_headers())
        if res.status_code == 200:
            rooms = [r for r in res.json() if r.get('status', 'active').startswith('active')]
            if rooms:
                for r in rooms:
                    s_dt = datetime.fromisoformat(r['start_time'].replace('Z', '+00:00')).astimezone(IL_TZ)
                    diff = get_now() - s_dt
                    total_sec = int(diff.total_seconds())
                    st.subheader(f"📍 {r['room_name']} | {r['name']}")
                    st.write(f"## **{total_sec//3600:02d}:{(total_sec%3600)//60:02d}:{total_sec%60:02d}**")
                    if st.button(f"💰 סיום", key=f"e_{r['id']}", use_container_width=True):
                        requests.patch(f"{MY_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished","end_time":get_now().isoformat()}, headers=get_my_headers())
                        st.rerun()
                    st.divider()
    active_timer()

with tab3:
    st.subheader("🧮 מחשבון")
    c1, c2, c3 = st.columns(3)
    c_tot, c_pay, c_min = c1.number_input("אנשים", 1, 50, 4), c2.number_input("משלמים", 1, 50, 4), c3.number_input("דקות", 1, 600, 60)
    # לוגיקת מחיר בסיסית לצורך המחשבון
    price = (c_min / 60) * 45 * c_tot
    st.metric("סה\"כ", f"₪{price:.2f}")

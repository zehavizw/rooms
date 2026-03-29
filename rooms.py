import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- הגדרות ---
S_URL = st.secrets['SUPABASE_URL']
S_KEY = st.secrets['SUPABASE_KEY']
M_URL = st.secrets['MY_URL']
M_KEY = st.secrets['MY_KEY']
IL_TZ = ZoneInfo("Asia/Jerusalem")

def get_now(): return datetime.now(IL_TZ)

# --- פונקציות ליבה ללא צורך בטוקן זמני ---
def get_headers(key):
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

def sync_data():
    # מושך 50 הזמנות אחרונות בצורה ישירה וקבועה
    res = requests.get(f"{S_URL}/rest/v1/bookings?select=*,room:rooms(*)&order=created_at.desc&limit=50", 
                       headers=get_headers(S_KEY), timeout=10)
    return res.json() if res.status_code == 200 else []

# --- ממשק ---
st.set_page_config(page_title="קריוקי זהבי", layout="centered")
st.title("🎤 ניהול חכם - גרסה יציבה")

# בחירת תאריך
view_date = st.date_input("📅 תאריך:", get_now().date())

if st.button("🔄 סנכרן נתונים", use_container_width=True):
    st.session_state.data = sync_data()
    st.success("הסנכרון הושלם!")

tab1, tab2, tab3 = st.tabs(["📅 לוח הזמנות", "⚡ פעילות", "🧮 מחשבון"])

with tab1:
    if 'data' in st.session_state:
        # סינון לפי התאריך שנבחר באפליקציה
        day_bookings = [b for b in st.session_state.data if (b.get('booking_date') or (b.get('start_time')[:10] if b.get('start_time') else '')) == view_date.strftime("%Y-%m-%d")]
        
        if day_bookings:
            # בדיקה מי כבר רץ אצלך
            res_a = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_headers(M_KEY))
            a_ids = [str(a['booking_id']) for a in res_a.json()] if res_a.status_code == 200 else []
            
            for b in day_bookings:
                bid = str(b['id'])
                if bid in a_ids: continue
                with st.expander(f"⏳ {b.get('customer_name') or 'לקוח'} | {b.get('start_time', '')[-5:]}"):
                    if st.button("🚀 כניסה", key=f"in_{bid}", use_container_width=True):
                        # שמירה במסד הפרטי שלך עם מפתח ה-Secret
                        payload = {"booking_id":bid,"name":b.get('customer_name'),"room_name":b.get('room',{}).get('name','חדר'),"start_time":get_now().isoformat(),"total_people":b.get('total_people',2),"paying_people":b.get('total_people',2),"planned_duration":b.get('duration_minutes',60),"status":"active"}
                        requests.post(f"{M_URL}/rest/v1/active_sessions", json=payload, headers=get_headers(M_KEY))
                        st.rerun()
        else: st.info("אין הזמנות ליום זה.")

with tab2:
    # שעון רץ לחדרים פעילים
    res = requests.get(f"{M_URL}/rest/v1/active_sessions", headers=get_headers(M_KEY))
    if res.status_code == 200:
        for r in [x for x in res.json() if x.get('status') == 'active']:
            st.subheader(f"📍 {r['room_name']} | {r['name']}")
            if st.button(f"💰 סיום", key=f"e_{r['id']}", use_container_width=True):
                requests.patch(f"{M_URL}/rest/v1/active_sessions?id=eq.{r['id']}", json={"status":"finished","end_time":get_now().isoformat()}, headers=get_headers(M_KEY))
                st.rerun()
            st.divider()

with tab3:
    st.subheader("🧮 מחשבון")
    c_tot = st.number_input("אנשים", 1, 50, 4)
    st.metric("סה\"כ (לפי 45 שח)", f"₪{c_tot * 45}")

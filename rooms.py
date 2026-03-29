import streamlit as st
from datetime import datetime, timedelta
import math

# הגדרות עיצוב לאייפון
st.set_page_config(page_title="קריוקי זהבי - ניהול מלא", layout="centered")

# CSS להתאמה אישית של צבעים וכפתורים
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 15px; height: 3.5em; font-weight: bold; }
    .status-free { color: #28a745; font-weight: bold; }
    .status-busy { color: #007bff; font-weight: bold; }
    .status-warning { color: #fd7e14; font-weight: bold; }
    .status-overtime { color: #dc3545; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# פונקציית המחירון המדויקת שלך
def calculate_price(num_people, total_hours):
    if total_hours <= 0: return 0
    if num_people == 1: rates = [50, 40, 30]
    elif 2 <= num_people <= 4: rates = [45, 35, 25]
    elif 5 <= num_people <= 9: rates = [40, 30, 20]
    else: rates = [35, 25, 15]
    
    total_cost = 0
    full_hours = math.floor(total_hours)
    extra_time = total_hours - full_hours
    
    for i in range(full_hours):
        total_cost += rates[min(i, 2)]
    
    if extra_time > 0:
        prev_rate_index = min(max(0, full_hours - 1), 2)
        if full_hours == 0: prev_rate_index = 0
        total_cost += extra_time * rates[prev_rate_index]
        
    return total_cost * num_people

# ניהול בסיס הנתונים בזיכרון (בשלב הבא נוכל לחבר לאקסל אמיתי)
if 'rooms' not in st.session_state:
    st.session_state.rooms = {i: {"status": "פנוי", "start": None, "end": None, "group": "", "people": 1, "duration": 60} for i in range(1, 4)}
if 'bookings' not in st.session_state:
    st.session_state.bookings = []

# תפריט עליון באייפון
tab1, tab2 = st.tabs(["📱 ניהול חדרים", '📅 לו"ז הזמנות'])
# --- לשונית 1: ניהול חדרים ---
with tab1:
    st.header("מצב חדרים נוכחי")
    for i in range(1, 4):
        room = st.session_state.rooms[i]
        with st.expander(f"חדר {i} - {room['status']}", expanded=(room['status'] != "פנוי")):
            if room["status"] == "פנוי":
                g_name = st.text_input("שם קבוצה", key=f"name_{i}")
                p_count = st.number_input("כמות אנשים", min_value=1, value=1, key=f"count_{i}")
                d_mins = st.number_input("זמן מוזמן (דקות)", min_value=15, value=60, step=15, key=f"dur_{i}")
                if st.button(f"התחל סשן בחדר {i}"):
                    st.session_state.rooms[i].update({
                        "status": "תפוס", "start": datetime.now(),
                        "end": datetime.now() + timedelta(minutes=d_mins),
                        "group": g_name, "people": p_count, "duration": d_mins
                    })
                    st.rerun()
            else:
                # חישוב זמנים
                now = datetime.now()
                time_left = room["end"] - now
                mins_left = time_left.total_seconds() / 60
                elapsed_hours = (now - room["start"]).total_seconds() / 3600
                
                # קביעת צבע סטטוס
                status_class = "status-busy"
                if mins_left <= 0: status_class = "status-overtime"
                elif mins_left <= 10: status_class = "status-warning"
                
                st.markdown(f"קבוצה: **{room['group']}** | אנשים: **{room['people']}**")
                
                if mins_left > 0:
                    st.markdown(f"זמן נותר: <span class='{status_class}'>{int(mins_left)} דקות</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span class='{status_class}'>חריגה של {int(abs(mins_left))} דקות!</span>", unsafe_allow_html=True)
                
                current_price = calculate_price(room["people"], elapsed_hours)
                st.metric("לתשלום כרגע", f"₪{current_price:.2f}")
                
                if st.button(f"סיום ותשלום חדר {i}", type="primary"):
                    st.session_state.rooms[i] = {"status": "פנוי", "start": None, "end": None, "group": "", "people": 1, "duration": 60}
                    st.success(f"הסשן הסתיים! סך הכל לגבות: ₪{current_price:.2f}")
                    st.rerun()

# --- לשונית 2: לו"ז הזמנות ---
with tab2:
    st.header("הזמנות עתידיות")
    with st.form("new_booking"):
        b_name = st.text_input("שם המזמין")
        b_room = st.selectbox("לאיזה חדר?", [1, 2, 3])
        b_people = st.number_input("כמה אנשים?", min_value=1, value=2)
        b_time = st.time_input("שעת הגעה")
        b_dur = st.number_input("משך זמן (דקות)", min_value=30, value=60, step=30)
        if st.form_submit_button('הוסף ללו"ז'):
            st.session_state.bookings.append({
                "name": b_name, "room": b_room, "people": b_people, 
                "time": b_time.strftime("%H:%M"), "duration": b_dur
            })
            st.rerun()
    
    st.divider()
    for idx, b in enumerate(st.session_state.bookings):
        col1, col2 = st.columns([3, 1])
        col1.write(f"🕒 {b['time']} | **{b['name']}** (חדר {b['room']}, {b['people']} איש)")
        if col2.button("צ'ק-אין", key=f"checkin_{idx}"):
            # מעביר את הנתונים לניהול החדרים
            st.session_state.rooms[b['room']].update({
                "status": "תפוס", "start": datetime.now(),
                "end": datetime.now() + timedelta(minutes=b['duration']),
                "group": b['name'], "people": b['people'], "duration": b['duration']
            })
            # מוחק מהלו"ז
            st.session_state.bookings.pop(idx)
            st.success(f"צ'ק אין בוצע לחדר {b['room']}!")
            st.rerun()

st.sidebar.button("רענן הכל 🔄")

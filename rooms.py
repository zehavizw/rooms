import streamlit as st
import requests

st.title("🔍 בדיקת מערכת סופית - זהבי")

# משיכת המפתחות מה-Secrets
S_URL = st.secrets.get('SUPABASE_URL')
S_KEY = st.secrets.get('SUPABASE_KEY')
M_URL = st.secrets.get('MY_URL')
M_KEY = st.secrets.get('MY_KEY')
R_TOKEN = st.secrets.get('REFRESH_TOKEN')

if st.button("🚀 הרץ בדיקת חיבורים"):
    st.write("---")
    
    # 1. בדיקת המערכת המקורית (Source)
    st.write("📡 **בודק חיבור למערכת המקורית...**")
    try:
        # ניסיון ראשון: עם הטוקן
        auth_url = f"{S_URL}/auth/v1/token?grant_type=refresh_token"
        res_auth = requests.post(auth_url, json={"refresh_token": R_TOKEN}, headers={"apikey": S_KEY}, timeout=5)
        if res_auth.status_code == 200:
            st.success("✅ REFRESH_TOKEN תקין!")
        else:
            st.error(f"❌ REFRESH_TOKEN לא תקין (קוד {res_auth.status_code}). הודעה: {res_auth.text}")
            
        # ניסיון שני: משיכת נתונים ישירה
        res_data = requests.get(f"{S_URL}/rest/v1/bookings?limit=1", headers={"apikey": S_KEY, "Authorization": f"Bearer {S_KEY}"}, timeout=5)
        if res_data.status_code == 200:
            st.success("✅ מפתח SUPABASE_KEY תקין למשיכת נתונים!")
        else:
            st.error(f"❌ מפתח SUPABASE_KEY חסום (קוד {res_data.status_code}).")
    except Exception as e:
        st.error(f"⚠️ שגיאה בחיבור למקור: {e}")

    st.write("---")

    # 2. בדיקת המערכת הפרטית שלך (My Database)
    st.write("🏠 **בודק חיבור למסד הנתונים הפרטי שלך...**")
    try:
        res_my = requests.get(f"{M_URL}/rest/v1/active_sessions?limit=1", headers={"apikey": M_KEY, "Authorization": f"Bearer {M_KEY}"}, timeout=5)
        if res_my.status_code == 200:
            st.success("✅ החיבור למסד הפרטי (MY_URL) תקין!")
        else:
            st.error(f"❌ שגיאה במסד הפרטי (קוד {res_my.status_code}). הודעה: {res_my.text}")
            if "JWT expired" in res_my.text:
                st.warning("השגיאה אומרת שהמפתח פג תוקף. את חייבת להשתמש במפתח ה-service_role!")
    except Exception as e:
        st.error(f"⚠️ שגיאה בחיבור למסד הפרטי: {e}")

st.divider()
st.write("אם הכל ירוק - הקוד תקין והבעיה היא בסינון התאריכים.")
st.write("אם יש אדום - תכתבי לי בדיוק מה השגיאה שמופיעה באדום.")

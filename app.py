#Streamlit Goal/Action Planner

import streamlit as st
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Date
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, scoped_session
from sqlalchemy_utils import database_exists, create_database
from werkzeug.security import generate_password_hash, check_password_hash

# ---------- DB setup ----------
DATABASE_URL = "sqlite:///goals_streamlit.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
if not database_exists(engine.url):
    create_database(engine.url)
SessionLocal = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    goals = relationship("Goal", back_populates="owner", cascade="all, delete-orphan")

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Goal(Base):
    __tablename__ = "goals"
    id = Column(Integer, primary_key=True)
    title = Column(String(250), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="goals")
    tasks = relationship("Task", back_populates="goal", cascade="all, delete-orphan")

    def progress(self):
        if not self.tasks:
            return 0.0
        completed = sum(1 for t in self.tasks if t.completed)
        return round((completed / len(self.tasks)) * 100, 1)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    title = Column(String(400), nullable=False)
    due_date = Column(Date, nullable=True)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    goal_id = Column(Integer, ForeignKey("goals.id"), nullable=False)
    goal = relationship("Goal", back_populates="tasks")


Base.metadata.create_all(bind=engine)

# ---------- Utilities ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def generate_tasks_for_goal(goal_title, days=7):
    """Simple deterministic task breakdown."""
    base = goal_title.strip()
    tasks = []
    if ',' in base or ';' in base:
        parts = [p.strip() for p in base.replace(';', ',').split(',') if p.strip()]
        for i, p in enumerate(parts):
            due = (datetime.utcnow().date() + timedelta(days=i))
            tasks.append({"title": p, "due_date": due})
        while len(tasks) < days:
            i = len(tasks)
            due = (datetime.utcnow().date() + timedelta(days=i))
            tasks.append({"title": f"Work on: {base} — step {i+1}", "due_date": due})
        return tasks[:days]
    for i in range(days):
        due = (datetime.utcnow().date() + timedelta(days=i))
        tasks.append({"title": f"Day {i+1}: Work on — {base}", "due_date": due})
    return tasks

# ---------- Streamlit UI helpers ----------
st.set_page_config(page_title="Goal/Action Planner", layout="wide")
st.title("Goal/Action Planner (Streamlit prototype)")

if "user_id" not in st.session_state:
    st.session_state.user_id = None

db = next(get_db())

# --- Authentication UI ---
def register_user(username, password):
    if not username or not password:
        return False, "Provide username and password."
    if db.query(User).filter_by(username=username).first():
        return False, "Username already exists."
    u = User(username=username)
    u.set_password(password)
    db.add(u)
    db.commit()
    return True, "Account created."

def login_user(username, password):
    u = db.query(User).filter_by(username=username).first()
    if not u or not u.check_password(password):
        return False, "Invalid credentials."
    st.session_state.user_id = u.id
    st.session_state.username = u.username
    return True, "Logged in."

def logout_user():
    st.session_state.user_id = None
    if "username" in st.session_state:
        del st.session_state.username

# Sidebar — Auth & navigation
with st.sidebar:
    st.header("Account")
    if st.session_state.user_id:
        st.markdown(f"**Logged in as:** {st.session_state.username}")
        if st.button("Logout"):
            logout_user()
            st.rerun()
    else:
        auth_tabs = st.tabs(["Login", "Register"])
        with auth_tabs[0]:
            uname = st.text_input("Username", key="login_user")
            pw = st.text_input("Password", type="password", key="login_pw")
            if st.button("Login", key="login_btn"):
                ok, msg = login_user(uname.strip(), pw)
                st.toast(msg) if ok else st.error(msg)
                if ok:
                    st.rerun()
        with auth_tabs[1]:
            runame = st.text_input("New username", key="reg_user")
            rpw = st.text_input("New password", type="password", key="reg_pw")
            if st.button("Register", key="reg_btn"):
                ok, msg = register_user(runame.strip(), rpw)
                st.toast(msg) if ok else st.error(msg)
                if ok:
                    st.success("You can now log in.")

    st.markdown("---")
    st.header("Demo")
    if st.button("Init demo DB"):
        # destructive reset for demo
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        demo = User(username="demo")
        demo.set_password("demo")
        db.add(demo)
        db.commit()
        st.success("Demo user created: demo / demo")
        st.rerun()

# If not logged in show landing info
if not st.session_state.user_id:
    st.subheader("Welcome")
    st.write(
        "This prototype demonstrates goal creation, automatic task breakdown, and progress tracking."
    )
    st.info("Register or login from the sidebar (demo: use the Init demo DB button, then login demo/demo).")
    st.stop()

# Logged-in user UI
current_user = db.query(User).get(st.session_state.user_id)
st.sidebar.markdown(f"User ID: {current_user.id}")

# Main columns
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Your Goals")
    goals = db.query(Goal).filter_by(user_id=current_user.id).order_by(Goal.created_at.desc()).all()
    if not goals:
        st.info("No goals yet. Create one below.")
    for g in goals:
        with st.expander(f"{g.title} — {g.progress()}% complete", True):
            st.write(g.description or "")
            tasks = db.query(Task).filter_by(goal_id=g.id).order_by(Task.due_date.asc(), Task.id.asc()).all()
            for t in tasks:
                key = f"task_{t.id}"
                colA, colB = st.columns([0.05, 0.95])
                checked = colA.checkbox("", value=bool(t.completed), key=key)
                if checked != t.completed:
                    t.completed = checked
                    db.commit()
                    st.rerun()
                colB.write(f"**{t.title}** — due: {t.due_date}" if t.due_date else f"**{t.title}**")
            st.markdown("---")
            if st.button("Delete goal", key=f"del_{g.id}"):
                db.delete(g)
                db.commit()
                st.rerun()

with col2:
    st.subheader("Create a New Goal")
    with st.form("create_goal"):
        title = st.text_input("Goal title")
        desc = st.text_area("Description (optional)", height=80)
        days = st.number_input("Number of daily tasks to create", min_value=1, max_value=30, value=7)
        submitted = st.form_submit_button("Create Goal & Generate Tasks")
        if submitted:
            if not title.strip():
                st.error("Please provide a title.")
            else:
                g = Goal(title=title.strip(), description=desc.strip(), owner=current_user)
                db.add(g)
                db.commit()
                tasks = generate_tasks_for_goal(title, days=days)
                for t in tasks:
                    tk = Task(title=t["title"], due_date=t["due_date"], goal=g)
                    db.add(tk)
                db.commit()
                st.success("Goal created with tasks.")
                st.rerun()

    st.markdown("---")
    st.subheader("Quick stats")
    total_goals = len(goals)
    total_tasks = db.query(Task).join(Goal).filter(Goal.user_id == current_user.id).count()
    completed_tasks = db.query(Task).join(Goal).filter(Goal.user_id == current_user.id, Task.completed == True).count()
    st.metric("Goals", total_goals)
    st.metric("Tasks (completed/total)", f"{completed_tasks}/{total_tasks}")
    if total_tasks:
        st.progress(completed_tasks / total_tasks)

# Footer notes
st.markdown("---")
st.caption("Prototype: simple auth and task generation. For production, add migrations, stronger security, and scheduled reminders.")

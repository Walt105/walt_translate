from flask import Flask, request, jsonify, send_from_directory, make_response
import os
import xml.etree.ElementTree as ET
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
from functools import wraps
from flask import request
from flask_apscheduler import APScheduler
import shutil
from datetime import datetime
import git
from pathlib import Path
import glob
import csv
import json
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt_identity,
    jwt_required,
)
import pyotp
from datetime import timedelta
from functools import wraps
import time

app = Flask(__name__, static_folder="static")
UPLOAD_FOLDER = "uploads"
DB_PATH = "translations.db"

# 配置日志记录器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("translation_app")
handler = RotatingFileHandler("app.log", maxBytes=1000000, backupCount=5)
formatter = logging.Formatter("%(asctime)s - %(ip)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


# 定义任务配置类
class Config:
    SCHEDULER_API_ENABLED = True
    GIT_REPO_URL = "https://github.com/Walt105/walt_translate.git"  # Git仓库URL
    GIT_REPO_PATH = "/uploads/walt_translate"  # 本地Git仓库路径
    TRANSLATION_FILES = {
        "pcb": {
            "type": "ts",
            "path": "pcb/librecad_zh_cn.ts",
        },
        "option": {"type": "csv_dir", "path": "option/"},
        "rmb": {"type": "csv", "path": "rmb/rmb.csv"},
        "menu": {"type": "menu_json", "path": "menu/"},  # 修改类型
        "message": {"type": "message_json", "path": "message/"},  # 修改类型
    }


app.config.from_object(Config)

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# 在app初始化后添加JWT配置
app.config["JWT_SECRET_KEY"] = "your-secret-key"  # 在生产环境中使用安全的密钥
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=8)
jwt = JWTManager(app)

# 添加动态密码配置
TRANSLATOR_SECRET = "base32secret3232"  # 生产环境使用安全的密钥
DEVELOPER_SECRET = "base32secret3233"  # 生产环境使用安全的密钥

translator_totp = pyotp.TOTP(TRANSLATOR_SECRET)
developer_totp = pyotp.TOTP(DEVELOPER_SECRET)


# 添加角色装饰器
def role_required(required_role):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            current_role = get_jwt_identity().get("role")
            if current_role != required_role and current_role != "developer":
                return jsonify({"msg": "Insufficient permissions"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 为不同类型的表创建不同的结构
    table_schemas = {
        "message": """
            CREATE TABLE IF NOT EXISTS message_translations
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             message_id TEXT,
             context TEXT,
             source TEXT,
             translation TEXT,
             status TEXT,
             comment TEXT,
             UNIQUE(context, message_id))
        """,
        "menu": """
            CREATE TABLE IF NOT EXISTS menu_translations
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             context TEXT,
             source TEXT,
             translation TEXT,
             status TEXT,
             comment TEXT)
        """,
        "pcb": """
            CREATE TABLE IF NOT EXISTS pcb_translations
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             context TEXT,
             source TEXT,
             translation TEXT,
             status TEXT,
             comment TEXT)
        """,
        "option": """
            CREATE TABLE IF NOT EXISTS option_translations
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             context TEXT,
             source TEXT,
             translation TEXT,
             status TEXT,
             comment TEXT)
        """,
        "rmb": """
            CREATE TABLE IF NOT EXISTS rmb_translations
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             context TEXT,
             source TEXT,
             translation TEXT,
             status TEXT,
             comment TEXT)
        """,
    }

    # 创建所有表
    for table, schema in table_schemas.items():
        c.execute(schema)

    conn.commit()
    conn.close()


def log_operation(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        ip = request.remote_addr
        url = request.url
        method = request.method
        logger.info(f"Request received: {method} {url}", extra={"ip": ip})
        response = func(*args, **kwargs)
        if isinstance(response, tuple):
            response = make_response(*response)
        logger.info(f"Response sent: {response.status}", extra={"ip": ip})
        return response

    return wrapper


@app.route("/get_translations", methods=["GET"])
def get_translations():
    tab = request.args.get("tab", "pcb")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        if tab == "message":
            # message表需要包含message_id字段
            c.execute(
                f"SELECT id, message_id, context, source, translation, status, comment FROM {tab}_translations"
            )
            translations = c.fetchall()
            result = [
                {
                    "id": t[0],
                    "message_id": t[1],
                    "context": t[2],
                    "source": t[3],
                    "translation": t[4],
                    "status": t[5],
                    "comment": t[6],
                }
                for t in translations
            ]
        else:
            # 其他表使用标准字段
            c.execute(
                f"SELECT id, context, source, translation, status, comment FROM {tab}_translations"
            )
            translations = c.fetchall()
            result = [
                {
                    "id": t[0],
                    "context": t[1],
                    "source": t[2],
                    "translation": t[3],
                    "status": t[4],
                    "comment": t[5],
                }
                for t in translations
            ]
    except sqlite3.OperationalError:
        result = []
    finally:
        conn.close()

    return jsonify(result)


@app.route("/update_translation", methods=["POST"])
@log_operation
def update_translation():
    data = request.json
    translation_id = data.get("id")
    new_translation = data.get("translation")
    new_status = data.get("status")
    tab = data.get("tab", "pcb")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        if tab == "message":
            # message表需要通过message_id和context来更新
            message_id = data.get("message_id")
            c.execute(
                f"""UPDATE {tab}_translations 
                    SET translation = ?, status = ? 
                    WHERE id = ? AND message_id = ?""",
                (new_translation, new_status, translation_id, message_id),
            )
        else:
            # 其他表使用标准更新方式
            c.execute(
                f"UPDATE {tab}_translations SET translation = ?, status = ? WHERE id = ?",
                (new_translation, new_status, translation_id),
            )
        conn.commit()
        return "Translation updated", 200
    except Exception as e:
        conn.rollback()
        logger.error(
            f"Error updating translation: {str(e)}", extra={"ip": request.remote_addr}
        )
        return f"Error updating translation: {str(e)}", 500
    finally:
        conn.close()


@app.route("/export_to_ts", methods=["POST"])
@role_required("developer")  # 仅开发者可以导出
@log_operation
def export_to_ts():
    data = request.json
    file_name = data.get("file_name")
    tab = data.get("tab", "pcb")
    if not file_name:
        return "File name is required", 400

    file_path = os.path.join(UPLOAD_FOLDER, file_name)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT * FROM {tab}_translations")
    translations = c.fetchall()
    conn.close()

    root = ET.Element("TS")
    contexts_dict = {}
    for t in translations:
        context_name = t[1]
        if context_name not in contexts_dict:
            context_elem = ET.SubElement(root, "context")
            ET.SubElement(context_elem, "name").text = context_name
            contexts_dict[context_name] = context_elem
        else:
            context_elem = contexts_dict[context_name]

        message = ET.SubElement(context_elem, "message")
        ET.SubElement(message, "source").text = t[2]
        translation_elem = ET.SubElement(message, "translation")
        translation_elem.text = t[3] or ""
        if t[4] == "unfinished":
            translation_elem.set("type", "unfinished")
        if t[4] == "obsolete":
            message.set("type", "obsolete")
        if t[5]:
            ET.SubElement(message, "comment").text = t[5]

    tree = ET.ElementTree(root)
    tree.write(file_path, encoding="utf-8", xml_declaration=True)

    return "File exported successfully", 200


@app.route("/import_from_ts", methods=["POST"])
@role_required("developer")  # 仅开发者可以导入
@log_operation
def import_from_ts():
    tab = request.form.get("tab", "pcb")
    if "file" not in request.files:
        return "No file part", 400
    file = request.files["file"]
    if file.filename == "":
        return "No selected file", 400

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    tree = ET.parse(file_path)
    root = tree.getroot()
    translations = []

    for context in root.iter("context"):
        context_name = (
            context.find("name").text if context.find("name") is not None else ""
        )
        for message in context.iter("message"):
            if "type" in message.attrib and message.attrib["type"] == "vanished":
                continue  # 跳过已消失的消息
            source_elem = message.find("source")
            if source_elem is None:
                continue  # 跳过没有源文本的消息
            source = source_elem.text or ""
            translation_elem = message.find("translation")
            if translation_elem is not None:
                translation = translation_elem.text or ""
                if (
                    "type" in translation_elem.attrib
                    and translation_elem.attrib["type"] == "unfinished"
                ):
                    status = "unfinished"
                else:
                    status = "translated"
            else:
                translation = ""
                status = "unfinished"

            if "type" in message.attrib and message.attrib["type"] == "obsolete":
                status = "obsolete"

            comment_elem = message.find("comment")
            comment = comment_elem.text if comment_elem is not None else ""

            translations.append((context_name, source, translation, status, comment))

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 创建表（如果不存在）
    c.execute(
        f"""CREATE TABLE IF NOT EXISTS {tab}_translations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  context TEXT,
                  source TEXT,
                  translation TEXT,
                  status TEXT,
                  comment TEXT)"""
    )
    # 清空表数据
    c.execute(f"DELETE FROM {tab}_translations")
    # 插入新数据
    c.executemany(
        f"INSERT INTO {tab}_translations (context, source, translation, status, comment) VALUES (?, ?, ?, ?, ?)",
        translations,
    )
    conn.commit()
    conn.close()

    return "File imported successfully", 200


@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_file(path):
    return send_from_directory(app.static_folder, path)


def backup_database():
    backup_folder = "db_backups"
    os.makedirs(backup_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_folder, f"translations_backup_{timestamp}.db")
    shutil.copy(DB_PATH, backup_file)
    logger.info(f"Database backed up to {backup_file}", extra={"ip": "Scheduler"})

    # 获取所有备份文件，按创建时间排序
    backups = sorted(
        [os.path.join(backup_folder, f) for f in os.listdir(backup_folder)],
        key=os.path.getctime,
    )
    # 如果备份文件超过 24 个，删除最旧的备份
    if len(backups) > 24:
        os.remove(backups[0])
        logger.info(f"Removed old backup file {backups[0]}", extra={"ip": "Scheduler"})


def init_git_repo():
    """初始化或更新git仓库"""
    repo_path = Path(app.config["GIT_REPO_PATH"])
    if not repo_path.exists():
        # 如果仓库不存在，执行clone
        git.Repo.clone_from(app.config["GIT_REPO_URL"], repo_path)
        logger.info("Git repository cloned successfully", extra={"ip": "System"})
    return git.Repo(repo_path)


def sync_from_git():
    try:
        repo = init_git_repo()
        repo.remotes.origin.pull()
        logger.info("Git repository pulled successfully", extra={"ip": "System"})

        for tab, file_config in app.config["TRANSLATION_FILES"].items():
            file_type = file_config["type"]
            file_path = Path(app.config["GIT_REPO_PATH"]) / file_config["path"]

            try:
                if file_type == "ts":
                    sync_ts_file(tab, file_path)
                elif file_type == "csv":
                    sync_csv_file(tab, file_path)
                elif file_type == "csv_dir":
                    sync_csv_directory(tab, file_path)
                elif file_type == "message_json":
                    sync_message_json(tab, file_path)
                elif file_type == "menu_json":
                    sync_menu_json(tab, file_path)
            except Exception as e:
                logger.error(f"Error syncing {tab}: {str(e)}", extra={"ip": "System"})

        return "Git sync completed successfully", 200
    except Exception as e:
        logger.error(f"Git sync failed: {str(e)}", extra={"ip": "System"})
        return f"Git sync failed: {str(e)}", 500


def sync_ts_file(tab, file_path):
    """同步单个ts文件"""
    if not file_path.exists():
        logger.warning(f"TS file not found: {file_path}", extra={"ip": "System"})
        return

    tree = ET.parse(file_path)
    root = tree.getroot()
    translations = []

    for context in root.iter("context"):
        context_name = (
            context.find("name").text if context.find("name") is not None else ""
        )
        for message in context.iter("message"):
            if "type" in message.attrib and message.attrib["type"] == "vanished":
                continue

            source_elem = message.find("source")
            if source_elem is None:
                continue

            source = source_elem.text or ""
            translation_elem = message.find("translation")

            if translation_elem is not None:
                translation = translation_elem.text or ""
                status = (
                    "unfinished"
                    if translation_elem.get("type") == "unfinished"
                    else "translated"
                )
            else:
                translation = ""
                status = "unfinished"

            translations.append((context_name, source, translation, status, ""))

    update_database(tab, translations)


def sync_csv_file(tab, file_path):

    if not file_path.exists():
        logger.warning(f"CSV file not found: {file_path}", extra={"ip": "System"})
        return

    translations = []
    context = file_path.stem

    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            f"SELECT source, status FROM {tab}_translations WHERE context = ?",
            (context,),
        )
        existing_translations = dict(c.fetchall())
        conn.close()

        for row in reader:
            source, translation = row
            status = existing_translations.get(source, "unfinished")
            translations.append((context, source, translation, status, ""))

    update_database(tab, translations)


def sync_csv_directory(tab, dir_path):
    """同步CSV文件夹"""
    if not dir_path.exists():
        logger.warning(f"CSV directory not found: {dir_path}", extra={"ip": "System"})
        return

    translations = []

    # 获取现有翻译的状态
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT context, source, status FROM {tab}_translations")
    existing_translations = {(row[0], row[1]): row[2] for row in c.fetchall()}
    conn.close()

    for csv_file in dir_path.glob("*.csv"):
        context = csv_file.stem

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)

            for row in reader:
                source, translation = row
                status = existing_translations.get((context, source), "unfinished")
                translations.append((context, source, translation, status, ""))

    update_database(tab, translations)


def sync_message_json(tab, dir_path):
    """同步message目录下的JSON文件,处理messages数组中的错误信息"""
    if not dir_path.exists():
        logger.warning(
            f"Message directory not found: {dir_path}", extra={"ip": "System"}
        )
        return

    translations = []

    # 获取现有翻译的状态
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        f"SELECT message_id, context, source, translation, status FROM {tab}_translations"
    )
    existing_translations = {
        (row[0], row[1]): (row[2], row[3], row[4]) for row in c.fetchall()
    }
    conn.close()

    # 遍历目录下的所有json文件
    for json_file in dir_path.glob("*.json"):
        try:
            context = json_file.stem  # 使用文件名作为context

            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

                # 处理messages数组
                if "messages" in data:
                    for message in data["messages"]:
                        # 使用name作为message_id
                        msg_id = message.get("name", "")
                        if not msg_id:  # 如果没有name，跳过
                            continue

                        # 使用description作为源文本
                        source = message.get("description", "")
                        if not source:  # 如果没有description，跳过
                            continue

                        # 获取现有的翻译和状态，如果不存在则使用默认值
                        existing = existing_translations.get(
                            (msg_id, context), ("", "", "unfinished")
                        )
                        existing_source, translation, status = existing

                        # 构建comment字段，包含错误信息的元数据
                        comment_data = {
                            "level": message.get("level", ""),
                            "revised": message.get("revised", ""),
                        }
                        comment = json.dumps(comment_data, ensure_ascii=False)

                        # 添加到translations列表
                        translations.append(
                            (
                                msg_id,  # message_id (name)
                                context,  # context (文件名)
                                source,  # source (description)
                                translation,  # translation (保持现有翻译)
                                status,  # status (保持现有状态)
                                comment,  # comment (JSON格式的错误信息元数据)
                            )
                        )

        except Exception as e:
            logger.error(
                f"Error processing message file {json_file}: {str(e)}",
                extra={"ip": "System"},
            )
            continue

    # 更新数据库
    update_database(tab, translations)


def update_database(tab, translations):
    """更新数据库的通用函数，根据不同的tab类型使用不同的更新逻辑"""
    if not translations:
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        if tab == "message":
            # message表的特殊处理
            c.execute(
                f"SELECT message_id, context, source, translation, status, comment FROM {tab}_translations"
            )
            existing_records = {(row[0], row[1]): row[2:] for row in c.fetchall()}

            updates = []
            inserts = []
            current_keys = set()

            for t in translations:
                key = (t[0], t[1])  # (message_id, context)
                current_keys.add(key)

                if key in existing_records:
                    existing_values = existing_records[key]
                    new_values = t[2:]  # (source, translation, status, comment)

                    # 只有当值不同时才更新
                    if existing_values != new_values:
                        updates.append(t)
                else:
                    inserts.append(t)

            # 找出需要删除的记录
            keys_to_delete = set(existing_records.keys()) - current_keys

            # 执行更新
            if updates:
                for t in updates:
                    c.execute(
                        f"""
                        UPDATE {tab}_translations 
                        SET source = ?, translation = ?, status = ?, comment = ?
                        WHERE message_id = ? AND context = ?
                        """,
                        (t[2], t[3], t[4], t[5], t[0], t[1]),
                    )

            # 执行插入
            if inserts:
                c.executemany(
                    f"""
                    INSERT INTO {tab}_translations 
                    (message_id, context, source, translation, status, comment)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    inserts,
                )

            # 执行删除
            if keys_to_delete:
                placeholders = ",".join(["(?,?)"] * len(keys_to_delete))
                delete_values = [val for key in keys_to_delete for val in key]
                c.execute(
                    f"""
                    DELETE FROM {tab}_translations 
                    WHERE (message_id, context) IN ({placeholders})
                    """,
                    delete_values,
                )

        else:
            # 其他表的标准处理
            c.execute(
                f"SELECT context, source, translation, status, comment FROM {tab}_translations"
            )
            existing_records = {(row[0], row[1]): row[2:] for row in c.fetchall()}

            updates = []
            inserts = []
            current_keys = set()

            for t in translations:
                key = (t[0], t[1])  # (context, source)
                current_keys.add(key)

                if key in existing_records:
                    existing_values = existing_records[key]
                    new_values = t[2:]  # (translation, status, comment)

                    # 只有当值不同时才更新
                    if existing_values != new_values:
                        updates.append(t)
                else:
                    inserts.append(t)

            # 找出需要删除的记录
            keys_to_delete = set(existing_records.keys()) - current_keys

            # 执行更新
            if updates:
                for t in updates:
                    c.execute(
                        f"""
                        UPDATE {tab}_translations 
                        SET translation = ?, status = ?, comment = ?
                        WHERE context = ? AND source = ?
                        """,
                        (t[2], t[3], t[4], t[0], t[1]),
                    )

            # 执行插入
            if inserts:
                c.executemany(
                    f"""
                    INSERT INTO {tab}_translations 
                    (context, source, translation, status, comment)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    inserts,
                )

            # 执行删除
            if keys_to_delete:
                placeholders = ",".join(["(?,?)"] * len(keys_to_delete))
                delete_values = [val for key in keys_to_delete for val in key]
                c.execute(
                    f"""
                    DELETE FROM {tab}_translations 
                    WHERE (context, source) IN ({placeholders})
                    """,
                    delete_values,
                )

        conn.commit()

        # 记录操作日志
        logger.info(
            f"Tab {tab}: Updated {len(updates)}, Inserted {len(inserts)}, Deleted {len(keys_to_delete)} translations",
            extra={"ip": "System"},
        )

    except Exception as e:
        conn.rollback()
        logger.error(
            f"Error updating database for {tab}: {str(e)}", extra={"ip": "System"}
        )
        raise
    finally:
        conn.close()


# 添加git同步的API端点
@app.route("/sync_from_git", methods=["POST"])
# @role_required("developer")  # 暂时注释掉认证要求
@log_operation
def handle_git_sync():
    return sync_from_git()


# 添加定时同步任务，每隔 24 小时执行一次
scheduler.add_job(
    id="git_sync_job",
    func=sync_from_git,
    trigger="interval",
    hours=24,
)

# 添加定时备份任务，每隔 24 小时执行一次
scheduler.add_job(
    id="backup_database_job", func=backup_database, trigger="interval", hours=24
)


# 添加登录路由
@app.route("/login", methods=["POST"])
def login():
    password = request.json.get("password", None)

    # 验证翻译者密码
    if translator_totp.verify(password):
        access_token = create_access_token(identity={"role": "translator"})
        return jsonify(access_token=access_token, role="translator"), 200

    # 验证开发者密码
    if developer_totp.verify(password):
        access_token = create_access_token(identity={"role": "developer"})
        return jsonify(access_token=access_token, role="developer"), 200

    return jsonify({"msg": "Invalid password"}), 401


# 获取当前动态密码（仅用于测试，生产环境中应通过其他安全渠道分发）
@app.route("/get_current_passwords", methods=["GET"])
def get_current_passwords():
    return jsonify(
        {
            "translator_password": translator_totp.now(),
            "developer_password": developer_totp.now(),
        }
    )


if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)

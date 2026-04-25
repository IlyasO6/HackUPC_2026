import shutil
import os

source_base = "../Frontend/mecalux_flask_ui_05"

print("Copiando templates...")
shutil.copytree(os.path.join(source_base, "templates"), "templates", dirs_exist_ok=True)

print("Copiando css...")
shutil.copytree(os.path.join(source_base, "static/css"), "static/css", dirs_exist_ok=True)

print("Copiando js...")
shutil.copytree(os.path.join(source_base, "static/js"), "static/js", dirs_exist_ok=True)

if os.path.exists(os.path.join(source_base, "static/favicon.ico")):
    shutil.copy(os.path.join(source_base, "static/favicon.ico"), "static/favicon.ico")

if os.path.exists("static/index.html"):
    shutil.move("static/index.html", "templates/editor.html")

print("¡Archivos del frontend bonito restaurados con éxito!")

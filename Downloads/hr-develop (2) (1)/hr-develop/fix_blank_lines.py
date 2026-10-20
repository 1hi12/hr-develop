import os

for root, _, files in os.walk("app"):
    for f in files:
        if not f.endswith(".py"):
            continue
        path = os.path.join(root, f)
        with open(path, "rb") as fh:
            content = fh.read()
        text = content.decode("utf-8")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        stripped = text.rstrip("\n")
        # Si le fichier ne contient que du vide -> on le vide completement
        # (un fichier 0 octet ne declenche jamais W391)
        new_text = "" if stripped == "" else stripped + "\n"
        if new_text != text:
            with open(path, "w", newline="\n") as fh:
                fh.write(new_text)
            print("Corrige:", path)

with open('Engine_1.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('log.info', 'print').replace('log.error', 'print').replace('log.debug', 'print').replace('log.warning', 'print')

with open('Engine_1.py', 'w', encoding='utf-8') as f:
    f.write(text)

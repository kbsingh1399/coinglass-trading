import ast

def replace_lines():
    with open('Engine_1.py', 'r', encoding='utf-8') as f:
        engine_src = f.read()
    engine_lines = engine_src.split('\n')
    
    with open('engine_components/coinglass_scraper.py', 'r', encoding='utf-8') as f:
        scraper_src = f.read()
    scraper_lines = scraper_src.split('\n')
    
    # engine_lines is 0-indexed, so 2586 corresponds to 2585
    # scraper_lines is 0-indexed, so 915 corresponds to 914
    
    new_engine = engine_lines[:2585] + scraper_lines[914:1158] + engine_lines[2884:]
    
    with open('Engine_1.py', 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_engine))

replace_lines()

import os

try:
    with open(r'E:\project-django\requirement.txt', 'r', encoding='utf-16') as f:
        content = f.read()
    
    print("--- CONTENT ---")
    print(content)
    print("---------------")
    
    # Save as standard UTF-8 requirements.txt
    with open(r'E:\project-django\requirements.txt', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Saved requirements.txt successfully as UTF-8!")
except Exception as e:
    print("Error:", e)

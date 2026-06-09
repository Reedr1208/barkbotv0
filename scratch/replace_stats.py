import re

for filename in ['api/index.html', 'public/index.html']:
    with open(filename, 'r') as f:
        content = f.read()

    # Replace the stat lines
    content = re.sub(
        r"if \(genderEl\) genderEl\.textContent = cleanGenderText\(dog\.gender \|\| 'Unknown'\);",
        "if (genderEl) genderEl.textContent = dog.sex || cleanGenderText(dog.gender || 'Unknown');",
        content
    )
    
    content = re.sub(
        r"dogAge\.textContent = cleanAgeText\(dog\.age \|\| 'Unknown'\);",
        "dogAge.textContent = dog.age_summary || cleanAgeText(dog.age || 'Unknown');",
        content
    )
    
    content = re.sub(
        r"dogWeight\.textContent = cleanWeightText\(dog\.weight \|\| 'Unknown'\);",
        "dogWeight.textContent = dog.weight_summary || cleanWeightText(dog.weight || 'Unknown');",
        content
    )

    with open(filename, 'w') as f:
        f.write(content)

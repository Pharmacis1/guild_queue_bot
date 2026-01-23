import requests

url = "http://ggfriends.net-forge.ru/api/upload"
file_path = "path/to/your/file.txt"  # Replace with your actual file path

with open(file_path, "rb") as f:
    files = {"file": f}
    response = requests.post(url, files=files)

print(response.status_code)
print(response.json())

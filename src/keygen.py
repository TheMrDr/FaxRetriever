import secrets

JWT_SECRET = secrets.token_hex(32)
print(JWT_SECRET)

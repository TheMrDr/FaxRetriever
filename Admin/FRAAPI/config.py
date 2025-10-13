# config.py

import getpass
import os
import secrets
from datetime import timedelta, timezone

# === Logging Statics ===
try:
    user = os.getlogin()
except OSError:
    user = os.environ.get("USERNAME", "unknown")
SYSTEM_ACTOR = f"{user}"

# === MongoDB Configuration ===
MONGO_URI = os.environ.get("FRA_MONGO_URI", "mongodb://10.2.0.10:27017")
DB_NAME = "fra2"
COL_RESELLERS = "resellers"
COL_CLIENTS = "clients"
COL_BEARERS = "bearer_tokens"
COL_LOGS = "access_logs"
COL_AUDIT_LOGS = "audit_logs"

# === JWT (v2.2, RS256 with kid rotation) ===
JWT_ISSUER = "https://licensing.clinicnetworking.com"
JWT_AUDIENCE = "FaxRetriever.api"
JWT_TTL_SECONDS = 86400
JWT_NOT_BEFORE_SKEW_SECONDS = 60
JWT_ACCEPT_LEEWAY_SECONDS = 60
REQUIRED_CLAIMS = [
    "iss",
    "aud",
    "sub",
    "device_id",
    "scope",
    "jti",
    "iat",
    "nbf",
    "exp",
]

# Active signing key id
JWT_ACTIVE_KID = "20250812-051355-371d"

# Private/Public key registry by kid
JWT_PRIVATE_KEYS = {
    "20250812-051355-371d": """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCmqra6Cr2GRJcX
nrdTlSLIPYIQZt4mJTX5aXcUFPAaIDojibTb4DVTkEFK5UzlenFtAPfL3MV0PDMh
3AC5hLUUHcjn5s1Liu8uBiBB1NxZHmgHGBb+V2T9R7vp+3En6AC9XVYV8+qUwhFE
1yga2vdxdqDDhx8CpHo0m2wtUq4U1MkZADbASufx/i1qtFnqISvRvpruluGf1fMx
Mb3vZ7T1UIgIKI13L8VBj8tBxwo0mt6AXLsL9iC2D/5Cnu7PqJofKXpOdWlpgZzl
rUUaG4IFB1/8Ggft2EW1r2VooN1it/Xc0UKsYqtuG5D3/OzvJT0zS+Zf58UZL5An
933rOD01AgMBAAECggEAFaolPIO+5SAvX8Oi4vuE3PCZ4pXslJrLrFMYRoT+PPcp
d4sj9lzrsaQTyK+L0lybN+cjTt2w0Q4uO12EvpjQjP/eKL7ousQhmSL0uHn59p+s
OBfajU9A8meLtruXlu9igTsLwKjHOnULl548OVlzRs170k7TKh3FQOdfJXkU5eIZ
NbXoYM/JpwH22IL2dwTX6CXlfOdbRhS8saNO/OcFtp3aGBbnVF4qyw6Gl5xVWcy4
ElHZ7u/0kwRszT+cpzCZx5cd9z2EdvxThBUbKBWZIwIX588ct7LYhV+en5jjGvGT
I/TCrBg155ViCrsbftHxMhG1rD+GcHulw69YtEe71QKBgQDeNuI0bjQ7j41lPtAp
Zla0ptxoCwOc0EwmUtcer71OK1+XiXkZmE2Lbk53wKmvfmi0EtFUgkaR4kl8ARlw
Lcib9tSc0h/qrlowk5zUdlUP7bDJIQzMPwEOFKFs5fBm72ULrxiTHeZkngtvhvww
hEpaeLXwZZLn7K4yj+w3kiCK0wKBgQDAAclxwZnUavyFYo8WV2Wl/IWIuBjOyhGa
6dVMojNpxlFwsSPit/vDkeLElIeNyyOYWfQ1gHav4jMd3ftbB0mmtHXA9QCNHDF5
lzERUFzIE9C/PxbVXeXYZH+m21pY02elpcarn9P+dRdxs+u5Uwq5vVpwSNjx9/HG
6S1PbzoC1wKBgG9aX2ZYpzIFkJxgqp1kXCSwzRgSFOBa/R3jO0t0U0+9qmxchmPO
D2XEg+u8jwuTM9Kw71cC5WwrUhmiz2WIe9O0D/z5yuamMinPfrJ1DdEqkgFn32rm
U5gDvJS+cQaUBjWhq5XlUNOw4xgjM3L4h+3oOXva2o//6ZcKyhtazZXjAoGAH2+r
da6G6xphIc2TM8s3X0fK7SmHFkRLQZvLSnK8DDNmHhdCktogpFJ8WEchMnvx5f3E
WAYiaIWWbOttPeghjOO6686xOmlFSG0SoY0Qw8lKwiUoLeLjwNwjckQztJtYOuy7
bFoMsXqmTf1xOLR56xMvfXbP3j4EHdcLjhfd3Z0CgYEAhDqMrL10+0UYwQCetSdG
TMHmPVIJNJ23F+YfT9rp/JcOXRecdQqvJarQtOb7yOWjAm5wddjl8GKO9bGlaTMg
xogWKVzM27QVZAhQ/A42rdg+k8ynok7YiJpgq5rya20q551vluKeVOwMnaNflo3q
v0AnrzmSRgNEQs9ZKF79USE=
-----END PRIVATE KEY-----"""
}

JWT_PUBLIC_KEYS = {
    "20250812-051355-371d": """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApqq2ugq9hkSXF563U5Ui
yD2CEGbeJiU1+Wl3FBTwGiA6I4m02+A1U5BBSuVM5XpxbQD3y9zFdDwzIdwAuYS1
FB3I5+bNS4rvLgYgQdTcWR5oBxgW/ldk/Ue76ftxJ+gAvV1WFfPqlMIRRNcoGtr3
cXagw4cfAqR6NJtsLVKuFNTJGQA2wErn8f4tarRZ6iEr0b6a7pbhn9XzMTG972e0
9VCICCiNdy/FQY/LQccKNJregFy7C/Ygtg/+Qp7uz6iaHyl6TnVpaYGc5a1FGhuC
BQdf/BoH7dhFta9laKDdYrf13NFCrGKrbhuQ9/zs7yU9M0vmX+fFGS+QJ/d96zg9
NQIDAQAB
-----END PUBLIC KEY-----"""
}

# === Bearer Token Cache Configuration ===
BEARER_REFRESH_OFFSET = timedelta(hours=1)  # refresh 1 hour before expiration
SKYSWITCH_TOKEN_URL = "https://telco-api.skyswitch.com/oauth2/token"
TOKEN_GRANT_TYPE = "password"

# === Logging ===
LOG_FILE = "fra_server.log"
LOG_LEVEL = "INFO"  # Options: DEBUG, INFO, WARNING, ERROR

# === Server ===
SERVER_PORT = int(os.environ.get("FRAAPI_PORT", "8000"))
SERVER_HOST = "0.0.0.0"

# === LibertyRx Integration ===
# Select environment for Liberty endpoint: "dev" or "prod"
LIBERTY_ENV = os.environ.get("LIBERTY_ENV", "dev").strip().lower()
LIBERTY_ENDPOINT_DEV = "https://devapi.libertysoftware.com"
LIBERTY_ENDPOINT_PROD = "https://api.libertysoftware.com"
# TTL for issued Liberty envelopes (seconds)
LIBERTY_ENVELOPE_TTL_SECONDS = int(os.environ.get("LIBERTY_ENVELOPE_TTL", "600"))  # default 10 minutes

# === Metadata ===
APP_VERSION = "2.2.0"

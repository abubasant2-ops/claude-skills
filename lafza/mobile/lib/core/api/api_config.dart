/// Base URL of the FastAPI backend. Override at build time:
/// flutter build web --dart-define=LAFZA_API_BASE=https://api.example/api/v1
/// (Android emulator needs http://10.0.2.2:8000/api/v1.)
const String kApiBase = String.fromEnvironment(
  'LAFZA_API_BASE',
  defaultValue: 'http://127.0.0.1:8000/api/v1',
);

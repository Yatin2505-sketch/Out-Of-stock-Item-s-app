# Stockbook web app (frontend)

React app for Stockbook. The shop computer doesn't need this folder to run:
a ready-built copy lives in `backend/static/`.

After changing anything here, rebuild and copy it over:

```
yarn install
yarn build
rm -rf ../backend/static && cp -r build ../backend/static
```

For live development: run the backend with `CORS_ORIGINS=http://localhost:3000`,
then run `REACT_APP_BACKEND_URL=http://localhost:8000 yarn start`.

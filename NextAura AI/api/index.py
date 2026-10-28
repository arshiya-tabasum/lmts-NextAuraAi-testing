from app import app

# Vercel Serverless Function entry point
# Exposes the Flask WSGI instance to Vercel
if __name__ == "__main__":
    app.run()

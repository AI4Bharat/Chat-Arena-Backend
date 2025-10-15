# Indic LLM Arena

A production-ready platform for interacting with and comparing leading LLMs from India. Built with Django REST Framework and React.

![Indic LLM Arena](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-green.svg)
![React](https://img.shields.io/badge/react-18.2+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## 🌟 Features

### Core Functionality
- **🤖 Multi-Model Chat** - Interact with various AI models from leading providers
- **🔄 Comparison Mode** - Compare responses from two models side-by-side
- **🎲 Random Mode** - Blind test models without knowing which is which
- **📊 Real-time Streaming** - Stream AI responses as they're generated
- **🌳 Message Branching** - Create conversation branches and explore different paths
- **📤 Share & Export** - Share conversations via links or export as JSON/Markdown/TXT

### Advanced Features
- **⭐ Comprehensive Feedback** - Rate responses and provide detailed feedback
- **🏆 ELO Leaderboard** - Track model performance with ELO ratings
- **🔐 Dual Authentication** - Google OAuth & Anonymous sessions
- **💾 Session Persistence** - Continue conversations across sessions
- **📱 Responsive Design** - Works seamlessly on desktop and mobile

## 🏗️ Architecture

### Backend (Django)
```
backend/
├── apps/
│   ├── user/          # User authentication and profiles
│   ├── ai_model/      # AI model registry and integration
│   ├── chat_session/  # Session management
│   ├── message/       # Message handling and streaming
│   ├── feedback/      # User feedback system
│   └── model_metrics/ # Performance tracking and leaderboards
├── core/              # Core settings and configurations
└── requirements.txt   # Python dependencies
```

### Frontend (React)
```
frontend/
├── src/
│   ├── app/          # App configuration and routing
│   ├── features/     # Feature-based modules
│   │   ├── auth/     # Authentication components
│   │   ├── chat/     # Chat interface and logic
│   │   ├── models/   # Model selection and testing
│   │   ├── feedback/ # Feedback components
│   │   └── leaderboard/ # Leaderboard views
│   ├── shared/       # Shared utilities and components
│   └── styles/       # Global styles
└── package.json      # Node dependencies
```

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis 6+
- Google Cloud account (for OAuth)

### Backend Setup

1. **Clone the repository**
```bash
git clone https://github.com/AI4Bharat/Chat-Arena.git
cd Chat-Arena/backend
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/ai_playground

# Redis
REDIS_URL=redis://localhost:6379

# AI Model API Keys
OPENAI_API_KEY=your-openai-key
GOOGLE_API_KEY=your-google-key
ANTHROPIC_API_KEY=your-anthropic-key
META_API_KEY=your-meta-key
MISTRAL_API_KEY=your-mistral-key

# Firebase/Auth
FIREBASE_CONFIG={"apiKey":"...","authDomain":"..."}

# Security
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
```

5. **Run migrations**
```bash
python manage.py migrate
python manage.py createsuperuser
```

6. **Start backend services**
```bash
# Terminal 1: Django server
python manage.py runserver

# Terminal 2: Celery worker
celery -A core worker -l info

# Terminal 3: Celery beat (for scheduled tasks)
celery -A core beat -l info
```

### Frontend Setup

1. **Navigate to frontend directory**
```bash
cd ../frontend
```

2. **Install dependencies**
```bash
npm install
```

3. **Set up environment variables**
```bash
cp .env.example .env
```

Edit `.env`:
```env
REACT_APP_API_URL=http://localhost:8000/api
REACT_APP_WS_URL=ws://localhost:8000/ws
REACT_APP_GOOGLE_CLIENT_ID=your-google-client-id
```

4. **Start development server**
```bash
npm run dev
```

The application will be available at `http://localhost:5173`

### Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google Identity Toolkit API
4. Create OAuth 2.0 credentials
5. Add authorized origins:
   - `http://localhost:5173` (development)
   - `https://your-domain.com` (production)

## 📱 Usage

### Chat Modes

1. **Direct Mode** - Chat with a single AI model
2. **Compare Mode** - Get responses from two models simultaneously
3. **Random Mode** - Blind test with randomly selected models

### Providing Feedback

- **Star Ratings** - Rate individual responses (1-5 stars)
- **Preferences** - Choose which model gave a better response
- **Categories** - Tag feedback with categories (accuracy, creativity, etc.)

### Viewing Leaderboards

- Filter by category (Overall, Creative Writing, Coding, Reasoning)
- View different time periods (Daily, Weekly, All-time)
- See detailed model performance metrics

## 🔧 Configuration

### Adding New AI Models

1. Create a model adapter in `backend/apps/ai_model/adapters/`
2. Register the model in Django admin
3. Add API credentials to environment variables

### Customizing Categories

Edit `backend/apps/feedback/constants.py` to add/modify feedback categories.

## 🚢 Deployment

### Backend Deployment (Example with Railway/Render)

1. Set up PostgreSQL and Redis instances
2. Configure environment variables
3. Deploy using provided `Dockerfile` or `railway.toml`

### Frontend Deployment (Example with Vercel)

```bash
npm run build
vercel --prod
```

## 📊 API Documentation

The API documentation is available at:
- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`

## 🧪 Testing

### Backend Tests
```bash
python manage.py test
```

### Frontend Tests
```bash
npm run test
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Built with assistance from Claude (Anthropic)** - AI pair programming and architecture design
- Thanks to all the AI model providers for their APIs
- The open-source community for the amazing tools and libraries

## 👨‍💻 Credits

This project was developed with significant assistance from **Claude 3 Opus**, an AI assistant by Anthropic. Claude helped with:
- System architecture design
- Code implementation
- Best practices and patterns
- Documentation
- Problem-solving and debugging

Special thanks to the Anthropic team for creating such a capable AI assistant that made building this complex project possible!

## 📞 Support

For support, please open an issue in the GitHub repository or contact the maintainers.

---

Built with ❤️ and AI assistance

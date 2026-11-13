# Outflo - AI Outreach Automation Platform

A production-ready, enterprise-grade SaaS platform for AI-powered outreach automation with lead generation, campaign management, and analytics.

## 🚀 Features

- **Lead Management** - Import, enrich, and manage leads with AI-powered data enrichment
- **Campaign Automation** - Create and manage email campaigns with sequences
- **AI Studio** - Generate personalized emails, analyze replies, and optimize outreach
- **Web Scraping** - Extract leads from websites, LinkedIn, Google Maps
- **Analytics Dashboard** - Real-time insights into campaign performance
- **Multi-tenant Architecture** - Organization-level access control
- **System Owner Panel** - Platform-wide management, plans, and monitoring
- **SMTP Integration** - Custom email sending configuration

## 🛠️ Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **MongoDB** - NoSQL database with motor async driver
- **JWT Authentication** - Secure token-based auth
- **RBAC** - Role-based access control

### Frontend
- **Next.js 14** - React framework with App Router
- **TailwindCSS** - Utility-first CSS framework
- **Framer Motion** - Animation library
- **Recharts** - Chart components
- **Lucide React** - Icon library
- **ShadCN** - UI component design system

## 📋 Requirements

- Python 3.9+
- Node.js 18+
- MongoDB (local or cloud)
- An AI provider API key (OpenAI, Anthropic, or any OpenAI-compatible endpoint)

## ⚡ Quick Start

### Option 1: Run Script (Windows)
```bash
.\run.bat
```

### Option 2: Manual Setup

**Backend:**
```bash
cd apps/backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd apps/frontend
npm install
npm run dev
```

## 🔐 Login Credentials

These seeded accounts are available in a fresh local database. Change the
passwords before deploying to production.

| Role | Email | Password | Login URL |
|------|-------|----------|-----------|
| System Owner (platform admin) | `admin@outflo.com` | `Admin@123` | http://localhost:3000/login |
| Organization Admin (Test Org) | `orgadmin@test.com` | `Test@1234` | http://localhost:3000/login |
| Organization Admin (Test Company) | `testorg@demo.com` | `Test@1234` | http://localhost:3000/login |
| Team Member (Test Company) | `teammember@test.com` | `Test@1234` | http://localhost:3000/login |

**Team Members:** inviting a member from **Team** creates a real login account
with the temporary password `Test@1234` (override with
`TEAM_MEMBER_DEFAULT_PASSWORD`). The invited user can sign in immediately and
change their password afterwards.

### Role access

| Area | System Owner | Org Admin | Team Member |
|------|--------------|-----------|-------------|
| System Owner panel (`/system-owner/*`) | ✅ | ❌ | ❌ |
| Platform-wide AI providers (no organization) | ✅ | ❌ | ❌ |
| Organization AI providers (`/app/ai-providers`) | ✅ (all orgs) | ✅ (own org) | Read only |
| Leads, campaigns, sequences | ✅ | ✅ | Per permissions |
| Billing, plans, organizations | ✅ | Read own | ❌ |

### AI provider setup

- Organization users: **AI Providers** → `http://localhost:3000/app/ai-providers`
- System owners: **System Owner → AI Providers** → `http://localhost:3000/system-owner/ai-providers`
- Add a provider with a name, type (OpenAI / Anthropic / Custom), base URL, and
  API key, then **Fetch models**, pick a default model, **Test**, and **Save**.
- Custom providers use the OpenAI-compatible protocol (Groq, Together, Azure
  OpenAI, OpenRouter, local gateways, etc.).

## 📁 Project Structure

```
Outflo/
├── apps/
│   ├── backend/          # FastAPI application
│   │   ├── app/
│   │   │   ├── api/      # API endpoints
│   │   │   ├── core/     # Core utilities
│   │   │   ├── db/       # Database connections
│   │   │   ├── models/  # MongoDB models
│   │   │   ├── middleware/ # Auth middleware
│   │   │   └── services/ # Business logic
│   │   └── tests/        # Backend tests
│   └── frontend/         # Next.js application
│       ├── app/
│       │   ├── app/      # User dashboard routes
│       │   ├── system-owner/ # Admin routes
│       │   ├── components/  # UI components
│       │   ├── hooks/    # React hooks
│       │   └── lib/      # Utilities
│       └── tests/        # Frontend tests
├── docs/                # Architecture docs
├── .env                 # Environment variables
├── run.bat              # Quick start script
├── Dockerfile.*         # Docker configs
└── docker-compose.yml   # Docker compose
```

## 🔧 Environment Variables

### Backend (.env)
```env
MONGO_URL=mongodb://localhost:27017
MONGO_DATABASE=outflo
SECRET_KEY=your-secret-key
DEBUG=true
PORT=8000
```

### Frontend (.env.local)
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

## 📡 API Documentation

Once backend is running:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 🧪 Testing

```bash
# Backend — use the project virtualenv, not global Python
cd apps/backend
venv\Scripts\activate
python -m pytest -q

# Frontend
cd apps/frontend
npm run test
```

## 🚢 Deploy (no Docker required)

Free hosting: **Vercel** (frontend) + **Render** (backend) + **MongoDB Atlas** (database).

Step-by-step guide: [docs/DEPLOY_VERCEL_RENDER.md](docs/DEPLOY_VERCEL_RENDER.md)

System Owner setup & test checklist: http://localhost:3000/system-owner/setup

## 🐳 Docker (optional)

Docker is optional for local/dev only. Production deploy does not require Docker.

## 📄 License

Private - All rights reserved

## 👨‍💻 Support

For issues and questions, contact the development team.
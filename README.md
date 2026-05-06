# Kisaan Project: Digital Advisory & Precision Farming

## 🌾 The Layman's Abstract
Kisaan Project is a **24/7 Digital Consultant** designed to live in a farmer's pocket. It replaces guesswork with space-age data. Instead of wondering why a crop is failing, the farmer uses the app to get "prescriptions" based on satellite imagery, real-time weather, and market prices. 

## 🚀 Core Functionalities
The system is built as a multi-module agricultural decision-support system:
*   **Satellite Health Checks:** Uses Sentinel Hub indices (NDVI, NDMI) to monitor crop health from space.
*   **Direct Expert Access:** A multimedia query system allowing farmers to send photos/videos of crop issues to a response team.
*   **Market Intelligence:** Live Mandi price tracking and caching for informed selling decisions.
*   **Accessibility First:** Automated Urdu audio generation and translation for farmers who prefer audio over text.
*   **Smart Reporting:** Generates comprehensive PDF reports based on the specific sowing date and crop stage.

## 🛠️ Technical Architecture
The platform is a "dual-track" system consisting of a high-performance backend and a cross-platform mobile frontend:

### Backend (The Brain)
*   **Framework:** Django 3.10.x & Django REST Framework.
*   **Database:** PostgreSQL (Production-grade relational storage).
*   **Auth:** JWT-based secure authentication using mobile numbers.
*   **Integrations:** Sentinel Hub API, OpenWeatherMap, and Custom Mandi Feeds.

### Mobile Frontend (The Interface)
*   **Framework:** React Native.
*   **Key Features:** Map-based farm marking, multipart media uploads, and persistent token authentication.

## 📦 Project Structure
The backend is modularized into feature-specific apps:
*   `User`: Authentication and farm mapping.
*   `Query`: Multimedia ticket system for farmer-expert interaction.
*   `Community`: Social engagement and knowledge sharing.
*   `Mandi`: Market price ingestion and filtering.
*   `Reports`: PDF engine and satellite data processing.

## ⚠️ Development Status & Security
This project is currently in the **Stabilization Phase**. 
**Current Priorities:**
1.  **Security Hardening:** Moving hardcoded secrets to environment variables.
2.  **API Consistency:** Standardizing the auth model between JWT and DRF tokens.
3.  **Refactoring:** Cleaning up the reporting pipeline and external service isolation.

## ⚙️ Setup Instructions
*(Coming Soon - Refer to the /docs folder for environment setup)*

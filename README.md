# SwiftCare API

A FastAPI backend for the SwiftCare healthcare application.

## Setup

1. Create a virtual environment:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root with the following contents:
   ```
   # MongoDB Settings
   MONGO_URI=mongodb://localhost:27017

   # JWT Settings
   JWT_SECRET=your_secure_jwt_secret_key_here
   ACCESS_TOKEN_EXPIRE_MINUTES=60

   # EmailJS Settings
   EMAILJS_USER_ID=your_emailjs_user_id
   EMAILJS_SERVICE_ID=your_emailjs_service_id
   EMAILJS_PRIVATE_KEY=your_emailjs_private_key_here
   EMAILJS_WELCOME_TEMPLATE=your_welcome_template_id
   EMAILJS_BOOKING_TEMPLATE=your_booking_template_id
   ```

4. Start the server:
   ```
   uvicorn main:app --reload
   ```

## Email Configuration

The application uses EmailJS for sending emails. To configure:

1. Create an account at [EmailJS](https://www.emailjs.com/)
2. Create a service with your email provider (Gmail, Outlook, etc.)
3. Create templates for welcome emails and booking confirmations
4. Get your User ID and Private Key from EmailJS dashboard
5. Update your `.env` file with the correct values

If the EmailJS private key is not provided, email sending will be attempted but may fail with a 403 error.

## API Endpoints

### Authentication
- `POST /auth/signup` - Register a new user
- `POST /auth/login` - Login and get JWT token

### Bookings
- `POST /bookings/` - Create a new booking
- `GET /bookings/` - List all bookings (with optional filters)
- `GET /bookings/{booking_id}` - Get a specific booking
- `PUT /bookings/{booking_id}` - Update a booking
- `DELETE /bookings/{booking_id}` - Cancel a booking 
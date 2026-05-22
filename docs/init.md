# Intelligent Multi-Source Guest Review Intelligence and Action Management System for The Kingsbury PLC

This project proposes a prototype decision-support system for The Kingsbury PLC to collect guest feedback from authorised review channels, analyse it using NLP techniques, identify recurring operational issues, and support management action through dashboards and ticket tracking. Guest feedback is distributed across platforms such as Google Business Profile, Booking.com, Tripadvisor, Reddit discussions, and other travel platforms; this fragmentation makes it difficult for management to identify repeated service issues, prioritise operational improvements, and track corrective actions. The project aims to transform multi-source guest feedback into structured operational insights and actionable department-level tasks.

The proposed solution is a **multi-source review ingestion, analysis, and action-management platform**. The system will be designed around authorised review-source integration rather than public web scraping. For the prototype, official business-account access will be simulated using mock API connectors shaped according to expected platform data structures. Google Business Profile, Booking.com, and Tripadvisor will be treated as verified review sources, while Reddit will be treated separately as a public social-listening source rather than a verified guest-review channel.

## Expected Scope to Cover

The prototype will include an authorised review-ingestion layer with mock connectors for Google Business Profile, Booking.com, Tripadvisor, Reddit, and a fallback mock dataset. All collected feedback will be normalised into a unified review model containing source platform, review ID, rating, review text, timestamp, review type, and action status. The NLP component will perform sentiment classification, issue-category detection, severity scoring, and department mapping. Identified issue categories may include service delays, room condition, cleanliness, food and beverage, noise/events, pricing concerns, and front-office issues.

The management dashboard will present sentiment distribution, platform-wise review trends, recurring issue categories, department-wise issue load, and high-severity reviews. The action-management workflow will allow selected reviews or detected issues to be converted into action tickets, assigned to relevant departments, prioritised, updated, and marked as resolved with notes. **The prototype will not include live Kingsbury credentials**, production hotel-system integration, web scraping, automated public replies, full CRM functionality, or revenue/pricing prediction.

## Technical Architecture and Implementation


The prototype will be implemented as a web-based system using React/Next.js for the frontend, FastAPI/Spring Boot for backend services, PostgreSQL for data storage, and a Python-based NLP pipeline using scikit-learn or Hugging Face models. Docker will be used for reproducible deployment during demonstration. Evaluation will be carried out using a manually labelled review dataset, classification accuracy and F1 score, functional workflow testing, and limited stakeholder-style feedback. 

## Deliverables

The main deliverables will be the review-ingestion prototype, unified dataset, NLP analysis pipeline, management dashboard, action-ticket workflow, evaluation results, and final project documentation. The prototype will be considered successful if it can import simulated multi-source reviews, normalise them, identify recurring issues, classify severity and department ownership, visualise insights, and demonstrate a complete review-to-action workflow.
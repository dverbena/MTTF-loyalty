from flask import Blueprint, request, jsonify, url_for
from dotenv import load_dotenv
from pydantic import ValidationError
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from smtplib import SMTP
import os
from io import BytesIO
import logging
from app.database import *
from app.crud import *
from app.models import *
from app.utils import generate_qr_code

# Initialize logger
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
EMAIL_HOST = os.getenv('EMAIL_HOST')
EMAIL_PORT = os.getenv('EMAIL_PORT')
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_FROM = os.getenv('EMAIL_FROM')

bp = Blueprint('customers', __name__, url_prefix='/customers')

@bp.route("/all", methods=["GET"])
def list_customers():
    logger.info("Received request to list all customers.")

    db = next(get_db())
    customers = get_customers(db)
    
    logger.debug(f"Fetched {len(customers)} customers from the database.")

    return jsonify([{
        "id": customer.id,
        "name": customer.name,
        "last_name": customer.last_name,
        "email": customer.email,
        "address": customer.address,
        "qr_code": customer.qr_code,
        "created_at": customer.created_at
    } for customer in customers])
    
@bp.route('/<int:id>', methods=['GET'])
def get_customer_by_id(id):    
    logger.info(f"Fetching info for customer_id: {id}")

    db = next(get_db())
    customer = db.query(Customer).filter(Customer.id == id).first()
    
    if not customer:
        logger.warning(f"Customer with id {id} not found.")
        return jsonify({"error": "Customer not found"}), 404
    
    logger.info(f"Found customer: {customer.name} {customer.last_name}")

    return jsonify({
        "id": customer.id,
        "name": customer.name,
        "last_name": customer.last_name,
        "email": customer.email,
        "address": customer.address,
        "qr_code": customer.qr_code,
        "created_at": customer.created_at
    }), 200

@bp.route("/qr/<qr_code>", methods=["GET"])
def get_customer_by_qr(qr_code):
    logger.info(f"Received request to get customer by QR code: {qr_code}")

    # Validate qr_code parameter using Pydantic model
    try:
        validated_data = QRCodeRequest(qr_code=qr_code)  # Validate the qr_code
        logger.debug(f"Validated QR code: {qr_code}")
    except ValidationError as e:
        logger.error(f"Invalid QR code format: {str(e)}")
        return jsonify({"error": f"Invalid QR code: {str(e)}"}), 400

    db = next(get_db())
    customer = db.query(Customer).filter(Customer.qr_code == validated_data.qr_code).first()

    if not customer:
        logger.warning(f"Customer with QR code {qr_code} not found.")
        return jsonify({"error": "Customer not found"}), 404

    logger.info(f"Found customer: {customer.name} {customer.last_name}")

    return jsonify({
        "id": customer.id,
        "name": customer.name,
        "last_name": customer.last_name,
        "email": customer.email,
        "address": customer.address,
        "qr_code": customer.qr_code,
        "created_at": customer.created_at
    }), 200

@bp.route("/search", methods=["GET"])
def get_customers_by_name():
    logger.info("Received request to search customers by name and/or last name.")

    # Validate query parameters with Pydantic
    try:
        # Validate the query parameters using Pydantic
        logger.debug("Validating search query parameters.")
        query_params = CustomerSearchQuery(
            name=request.args.get("name"),
            last_name=request.args.get("last_name")
        )
        logger.debug(f"Validated query parameters: {query_params.dict()}")
    except ValidationError as e:
        logger.error(f"Invalid query parameters: {str(e)}")
        return jsonify({"error": str(e)}), 400

    # Ensure at least one parameter is provided
    if not query_params.name and not query_params.last_name:
        logger.error("Neither 'name' nor 'last_name' was provided.")
        return jsonify({"error": "At least one of 'name' or 'last_name' must be provided."}), 400

    db = next(get_db())

    # Build the query based on the available parameters
    query = db.query(Customer)
    if query_params.name:
        query = query.filter(Customer.name == query_params.name)
    if query_params.last_name:
        query = query.filter(Customer.last_name == query_params.last_name)

    customers = query.all()

    if not customers:
        logger.warning(f"No customers found matching the search criteria.")
        return jsonify({"error": "No customers found"}), 404

    logger.info(f"Found {len(customers)} customers matching the search criteria.")

    return jsonify([{
        "id": customer.id,
        "name": customer.name,
        "last_name": customer.last_name,
        "email": customer.email,
        "address": customer.address,
        "qr_code": customer.qr_code,
        "created_at": customer.created_at
    } for customer in customers]), 200

@bp.route("/add", methods=["POST"])
def create_new_customer():
    logger.info("Received request to create a new customer.")

    try:
        data = CustomerCreateRequest(**request.get_json())  # Validate request body using Pydantic
        logger.debug(f"Validated customer creation data: {data.dict()}")
    except ValidationError as e:
        logger.error(f"Validation error while creating customer: {str(e)}")
        return jsonify({
            "error": "Invalid data provided",
            "details": str(e)
        }), 400

    try:
        db = next(get_db())
        customer = create_customer(db, data.name, data.last_name, data.email, data.address)

        logger.info(f"Created new customer with ID: {customer.id}, Name: {customer.name} {customer.last_name}")

        return jsonify({
            "id": customer.id,
            "name": customer.name,
            "last_name": customer.last_name,
            "email": customer.email,
            "address": customer.address,
            "qr_code": customer.qr_code,
            "created_at": customer.created_at
        }), 201

    except Exception as e:
        # Catch any other exceptions (e.g., database errors)
        logger.error(f"Error while creating customer: {str(e)}")
        return jsonify({
            "error": "An unexpected error occurred while creating the customer.",
            "details": str(e)
        }), 500

def send_email_with_attachment_and_inline_image(to_email, attachment):
    """
    Send an email with an attachment and an inline image using the SMTP configuration from the environment.

    Args:
        to_email (str): Recipient's email address.
        subject (str): Email subject.
        attachment (BytesIO): File to attach (in-memory file object).
        attachment_filename (str): The name of the attachment file.
        inline_image_path (str): Path to the image to include inline.
    """
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("", smtp_user)

    if not all([smtp_server, smtp_port, smtp_user, smtp_password, sender_email]):
        raise ValueError("Missing SMTP configuration in the environment variables.")

    # Construct the email
    message = MIMEMultipart("related")
    message["From"] = sender_email
    message["To"] = to_email
    message["Subject"] = "Il tuo codice MTTF"

    # Add the HTML body
    msg_alternative = MIMEMultipart("alternative")
    message.attach(msg_alternative)

    # Embed the inline image using CID
    cid = "mttf-logo"
    html_body = f"""
    <div style="text-align: center;">
        <img src="cid:{cid}" alt="MTTF Logo" width="398" height="398">
        <div style="font-size: 24px; font-family: 'Google Sans', Roboto, Arial, sans-serif; line-height: 32px; margin-top: 24px;">
            In allegato il codice da presentare per accumulare punti premio presso MTTF.<br>
            Puoi conservare questa email o salvare l'immagine sul tuo dispositivo.
        </div>
    </div>
    """
    msg_alternative.attach(MIMEText(html_body, "html"))

    # Attach the inline image
    with open("/app/frontend/static/mttf.jpg", "rb") as img:
        img_part = MIMEImage(img.read())
        img_part.add_header("Content-ID", f"<{cid}>")
        img_part.add_header("Content-Disposition", "inline", filename="mttf-logo.png")
        message.attach(img_part)

    # Attach the QR code file
    part = MIMEBase("application", "octet-stream")
    part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename={'qrcode.png'}",
    )
    message.attach(part)

    # Send the email
    with SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)


@bp.route('/send-qr-code', methods=['POST'])
def send_qr_code():
    try:          
        logger.info("Received request to send the QR code to customer")
        
        try:
            data = IDQuery(**request.get_json())  # Validate request body using Pydantic
            logger.debug(f"Validated send-qr-code data: {data.dict()}")
        except ValidationError as e:
            logger.error(f"Validation error: {str(e)}")
            return jsonify({
                "error": "Invalid data provided",
                "details": str(e)
            }), 400

        db = next(get_db())
        customer = db.query(Customer).filter(Customer.id == data.id).first()
    
        if not customer:
            logger.warning(f"Customer with id {id} not found.")
            return jsonify({"error": "Customer not found"}), 404
        
        logger.info(f"Found customer: {customer.name} {customer.last_name}")        

        # Generate the QR code as an image
        qr_code_image = generate_qr_code(customer.qr_code)
        
        # Prepare the email
        send_email_with_attachment_and_inline_image(
            to_email=customer.email,
            attachment=qr_code_image
        )

        return jsonify(
            {
                "message": f"QR code sent to {customer.email}", 
                "customer": 
                { 
                    "name": f"{customer.name}", 
                    "last_name": f"{customer.last_name}"
                }
            }), 200

    except Exception as e:
            return jsonify({
                "error": "error",
                "details": str(e)
            }), 400
    
@bp.route("/<int:id>", methods=["DELETE"])
def delete_customer(id):
    """
    Delete a customer by ID.
    
    Args:
        id (int): The ID of the customer to be deleted.
    
    Returns:
        JSON response indicating success or failure.
    """
    logger.info(f"Received request to delete customer with ID: {id}")

    db = next(get_db())
    customer = db.query(Customer).filter(Customer.id == id).first()

    if not customer:
        logger.warning(f"Customer with ID {id} not found.")
        return jsonify({"error": "Customer not found"}), 404

    try:
        db.delete(customer)
        db.commit()
        logger.info(f"Customer with ID {id} deleted successfully.")
        
        return jsonify(
            {
                "message": f"Customer with ID {id} has been deleted.",
                "customer": 
                { 
                    "name": f"{customer.name}", 
                    "last_name": f"{customer.last_name}"
                }
            }), 200

    except Exception as e:
        logger.error(f"Error occurred while deleting customer with ID {id}: {str(e)}")
        db.rollback()
        return jsonify({"error": "An error occurred while deleting the customer.", "details": str(e)}), 500

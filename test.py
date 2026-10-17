import cv2
from ultralytics import YOLOE

# Load pretrained model
model = YOLOE("yoloe-11s-seg.pt")

# Tell YOLO what objects to look for
# model.set_classes([
#     "plastic water bottle",
#     "aluminum soda can",
#     "cardboard box",    
#     "paper cup",
#     "banana",
#     "glass bottle",
#     "marker"
# ])


model.set_classes([
    "bottle",
    "can",
    "cup",
    "paper",
    "cardboard box",
    "banana",
    "apple",
    "plastic bag",
    "food container",
    "food wrapper",
    "newspaper",
    "plastic container",
    "expo marker",
    "eraser"
])






# Open your laptop webcam
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    raise RuntimeError("Could not open webcam")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Run AI detection
    results = model.predict(frame, conf=0.25, verbose=False)

    # Draw bounding boxes, labels, and segmentation masks
    annotated = results[0].plot()

    # Show live result
    cv2.imshow("AI Trash Detection", annotated)

    # Press Q to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
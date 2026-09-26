import glob
import os
import pickle
import time

import cv2
import face_recognition as fr

from src.integrations.arduino_controller import ArduinoController, reset_buffers
from src.modules.shared_data import set_name

min_x = 0
max_x = 180
min_y = 60
max_y = 130

font_scale = 0.7
blue = (255, 0, 0)
green = (0, 255, 0)
red = (0, 0, 255)
white = (255, 255, 255)


def open_video_capture(devices=None):
    if devices is None:
        # devices = ["/dev/video3", 0]
        devices = []
        devices = glob.glob("/dev/video*")
        devices.append(0)

    for device in devices:
        try:
            cap = cv2.VideoCapture(device)
            if cap.isOpened():
                print(f"Opened video capture device: {device}")
                return cap
        except cv2.error as e:
            print(f"Error opening {device}: {e}")

    print("None of the specified devices could be opened.")
    return None


def load_images(path, resize=1):
    images_path = glob.glob(path)
    # print(images_path)
    images = []
    names = []
    for image_path in images_path:
        name = os.path.basename(image_path).split(".")[0]
        image = cv2.imread(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if resize < 1:
            width, height, _ = image.shape
            image = cv2.resize(image, (int(width * resize), int(height * resize)))

        images.append(image)
        names.append(name)

    print(f"Images loaded from: {path}")

    return {"images": images, "names": names}


def encode_images(images):
    encoded_images = []
    length = len(images["images"])
    names = images["names"]
    directory = "data/image-encodings"

    # Check if the directory exists
    if not os.path.exists(directory):
        os.makedirs(directory)

    for i, image in enumerate(images["images"]):
        file_path = os.path.join(directory, f"{names[i]}.pkl")

        if os.path.exists(file_path):
            print(f"Loading face encoding: {i + 1}/{length}")
            with open(file_path, "rb") as f:
                encodings = pickle.load(f)
            encoded_images.append(encodings)
        else:
            print(f"Generating face encoding: {i + 1}/{length}")
            encoded_image = fr.face_encodings(image)[0]
            # encoded_images.append({"face_encoding": encoded_image, "name": image["name"]})
            encoded_images.append(encoded_image)
            with open(file_path, "wb") as f:
                pickle.dump(encoded_image, f)

    return encoded_images


def face_recognition_v1(path):
    images = load_images(path)
    encoded_images = encode_images(images)

    cap = open_video_capture()

    cap.set(3, 512)  # width
    cap.set(4, 512)  # height

    resize = 1

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) * resize)
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) * resize)
    print(f"frame width: {frame_width}, height: {frame_height}")

    while cap.isOpened():
        t = time.time()

        # Read frame from video
        success, frame = cap.read()
        if not success:
            break
        frame = cv2.resize(frame, (frame_width, frame_height))
        # frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        time.time()
        faceLocations = fr.face_locations(frame)
        # print(f"Found {len(faceLocations)}")
        # et = time.time() - t0
        # print(f"Face locations time: {et:.3f} sec")

        if len(faceLocations) > 0:
            time.time()
            person_encodings = fr.face_encodings(frame)
            # et = time.time() - t1
            # print(f"Face encodings time: {et:.3f} sec")

            t2 = time.time()
            for i, person_encoding in enumerate(person_encodings):
                result = fr.compare_faces(encoded_images, person_encoding, tolerance=0.55)  # face comparison time is < 1 ms
                if True in result:
                    for j, val in enumerate(result):
                        if val:
                            name = images["names"][j]
                            cv2.putText(frame, name, (faceLocations[i][3], faceLocations[i][0] - 50), cv2.FONT_HERSHEY_COMPLEX, font_scale, green, 2)
                            cv2.rectangle(frame, (faceLocations[i][3], faceLocations[i][0]), (faceLocations[i][1], faceLocations[i][2]), white, 2)
                else:
                    name = "Unknown"
                    cv2.putText(frame, name, (faceLocations[i][3], faceLocations[i][0] - 50), cv2.FONT_HERSHEY_COMPLEX, font_scale, green, 2)
                    cv2.rectangle(frame, (faceLocations[i][3], faceLocations[i][0]), (faceLocations[i][1], faceLocations[i][2]), white, 2)
            et = time.time() - t2
            print(f"Face comparison time: {et:.3f} sec")

        else:
            # Handle the case when no faces are detected
            print("No faces detected in the frame.")

        cv2.imshow("Face Detection ", frame)

        et = time.time() - t
        print(f"Face recognition time: {et:.3f} sec")
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # Release the VideoCapture and close the windows
    cap.release()
    cv2.destroyAllWindows()


def face_recognition_v2(images_dir, arduino_controller: ArduinoController):
    images = load_images(images_dir)
    encoded_images = encode_images(images)
    cap = open_video_capture()

    frame_width = 720
    frame_height = 640
    resize = 1
    cap.set(3, frame_width)  # width
    cap.set(4, frame_height)  # height

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    new_width = int(frame_width * resize)
    new_height = int(frame_height * resize)
    print(f"frame width: {frame_width}, height: {frame_height}")

    cam_cx = int(frame_width / 2)
    cam_cy = int(frame_height / 2)
    fx = cam_cx / 8
    fy = cam_cy / 8
    x_axis, y_axis = 90, 90
    prev_x, prev_y = 90, 90

    prev_time = 0
    ms = time.time()
    print_logs = False
    xk = False
    yk = True
    gk = False

    while cap.isOpened():
        t = time.time()

        success, frame = cap.read()
        if not success:
            break

        # Flip the frame horizontally for a later selfie-view display
        frame = cv2.flip(frame, 1)
        frame_resized = cv2.resize(frame, (new_width, new_height))

        t0 = time.time()
        faceLocations = fr.face_locations(frame_resized)

        if print_logs:
            print(f"Found {len(faceLocations)}")
            et = time.time() - t0
            print(f"Face locations time: {et:.3f} sec")

        curr_time = time.time()
        fps = 1 / (curr_time - prev_time)
        prev_time = curr_time
        names = []
        _minx1, _maxx1, _miny1, _maxy1 = frame_width, 0, frame_height, 0
        y1, x2, y2, x1 = 0, 0, 0, 0

        if len(faceLocations) > 0:
            t1 = time.time()

            person_encodings = fr.face_encodings(frame_resized, known_face_locations=faceLocations)
            if print_logs:
                et = time.time() - t1
                print(f"Face encodings time: {et:.3f} sec")

            t2 = time.time()
            for i, face_loc in enumerate(faceLocations):
                result = fr.compare_faces(encoded_images, person_encodings[i], tolerance=0.55)  # face comaprison time is < 1 ms
                if True in result:
                    for j, val in enumerate(result):
                        if val:
                            name = images["names"][j]
                            names.append(name)
                            set_name(names)
                            print(f"Face location: {face_loc}")
                            y1, x2, y2, x1 = face_loc
                            y1, x2, y2, x1 = int(y1 / resize), int(x2 / resize), int(y2 / resize), int(x1 / resize)

                            cv2.putText(frame, name, (x1, y1 - 20), cv2.FONT_HERSHEY_COMPLEX, font_scale, green, 2)
                            cv2.rectangle(frame, (x1, y1), (x2, y2), white, 2)

                else:
                    name = "Unknown"
                    names.append(name)
                    set_name(names)
                    y1, x2, y2, x1 = face_loc
                    y1, x2, y2, x1 = int(y1 / resize), int(x2 / resize), int(y2 / resize), int(x1 / resize)

                    cv2.putText(frame, name, (x1, y1 - 20), cv2.FONT_HERSHEY_COMPLEX, font_scale, green, 2)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), white, 2)

                if print_logs:
                    et = time.time() - t2
                    print(f"Face comparison time: {et:.3f} sec")

                x = int((x1 + x2) / 2)
                y = int((y1 + y2) / 2)
                diff_x = x - cam_cx
                diff_y = y - cam_cy
                adj_x = int(diff_x / fx)
                adj_y = -int(diff_y / fy)
                x_axis += adj_x
                y_axis += adj_y

                p = 0.5
                x_axis = prev_x * (1 - p) + x_axis * p
                y_axis = prev_y * (1 - p) + y_axis * p

                if print_logs:
                    print(f"cam_cx: {cam_cx}, cam_cy: {cam_cy}, x: {x}, y: {y}, adj_x: {adj_x}, adj_y: {adj_y}, x_axis: {x_axis}, y_axis: {y_axis}")

                t3 = time.time()
                arduino_controller.servo_move(x_axis, y_axis, True)
                if print_logs:
                    print(f"Arduino communication time:{(time.time() - t3):.3f} sec")
                ms = time.time()

        else:
            deg = 10
            if time.time() - ms > 1:
                ms = time.time()
                print("No faces detected in the frame.")
                if x_axis > min_x or x_axis < max_x:
                    if xk:
                        x_axis += deg
                        x_axis = min(x_axis, max_x)
                    else:
                        x_axis -= deg
                        x_axis = max(min_x, x_axis)

                    if x_axis == min_x:
                        xk = True
                        gk = True
                    if x_axis == max_x:
                        xk = False
                        gk = True

                    if gk and (y_axis > min_y or y_axis < max_y):
                        if yk:
                            y_axis += deg
                            y_axis = min(y_axis, max_y)
                        else:
                            y_axis -= deg
                            y_axis = max(min_y, y_axis)

                        if y_axis == min_y:
                            yk = True
                        if y_axis == max_y:
                            yk = False
                        gk = False

                t3 = time.time()
                arduino_controller.servo_move(x_axis=x_axis, y_axis=y_axis)
                print(f"Arduino communication time:{(time.time() - t3):.3f} sec")

        cv2.putText(frame, f"FPS: {int(fps)}", (5, 25), cv2.FONT_HERSHEY_COMPLEX, font_scale, green, 2)

        cv2.imshow("Face Detection", frame)
        reset_buffers()

        if print_logs:
            et = time.time() - t
            print(f"Face recognition time: {et:.3f} sec")

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # Release the VideoCapture and close the windows
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    path = "data/images-samples/*"
    # face_recognition_v1(path)
    arduino_controller = ArduinoController()
    face_recognition_v2(path, arduino_controller)
    # images = load_images(path)
    # result = fr.batch_face_locations(images['images'], number_of_times_to_upsample=2)
    # print(result)

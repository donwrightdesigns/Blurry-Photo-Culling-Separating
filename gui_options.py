# gui_options.py

def get_image_path(photo):
    # Placeholder function to mimic the behavior of get_image_path
    return photo

def main():
    # Main functionality to handle user selectable options
    selected_format = input("Select image format (JPG/RAW): ")
    
    if not selected_format:
        print("No input provided. Please select a valid format.")
        return
    
    if selected_format.upper() == "JPG":
        print("Selected JPG format")
    elif selected_format.upper() == "RAW":
        print("Selected RAW format")
    else:
        print("Invalid format. Please select JPG or RAW.")

if __name__ == "__main__":
    main()

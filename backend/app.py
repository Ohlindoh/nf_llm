from flask import Flask, request, jsonify, render_template
import nlp_module
import optimization_module

app = Flask(__name__, template_folder='../templates', static_folder='../static')

@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/interpret', methods=['POST'])
def interpret():
    try:
        print("Received POST request on /interpret")
        user_input = request.json['user_input']
        print("User input received:", user_input)

        # Process input with NLP module
        #processed_input = nlp_module.natural_language_to_code(user_input)
        user_constraints = ""
        processed_input = optimization_module.run_optimization(user_constraints)

        
        # Log processed input
        print("Processed input:", processed_input)

        # Return the results
        return jsonify(processed_input)

    except Exception as e:
        print("Error in /interpret:", str(e))
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True)

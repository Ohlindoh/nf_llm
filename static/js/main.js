document.addEventListener('DOMContentLoaded', (event) => {
    document.getElementById('generateButton').addEventListener('click', submitPrompt);
});

async function submitPrompt() {
    console.log("submitPrompt called");  // Confirm function call
    const userInput = document.getElementById('userInput').value;
    console.log("User Input:", userInput);  // Log user input

    try {
        console.log("Sending request to /interpret");
        const response = await fetch('http://127.0.0.1:5000/interpret', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_input: userInput })
        });
        console.log("Request sent, response received");

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        document.getElementById('codeArea').textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        console.error('Error during fetch operation:', error);
    }
}


// async function runCode() {
//     try {
//         const params = {};  // Get these from the codeArea or elsewhere
//         const response = await fetch('http://127.0.0.1:5000/optimize', {
//             method: 'POST',
//             headers: { 'Content-Type': 'application/json' },
//             body: JSON.stringify({ params })
//         });
        
//         if (!response.ok) {
//             throw new Error("Network response was not ok");
//         }
        
//         const lineup = await response.json();
//         document.getElementById('resultArea').textContent = JSON.stringify(lineup, null, 2);
//     } catch (error) {
//         console.error('There was a problem with the fetch operation:', error);
//     }
// }

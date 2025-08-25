from dotenv import load_dotenv
from strategies.ai_strategy import AIStrategy

def run_test():
    """
    A simple test to see the AIStrategy in action.
    """
    print("--- Starting AI Strategy Test ---")
    
    # 1. Load the OPENAI_API_KEY from your .env file
    load_dotenv()
    
    # 2. Create a dummy config object (since AIStrategy needs one)
    class DummyConfig:
        pass
    cfg = DummyConfig()
    
    # 3. Initialize your AIStrategy
    ai_strategy = AIStrategy(cfg)
    
    # 4. Run one analysis cycle
    print("\nRequesting analysis from AI...")
    sentiment = ai_strategy.run_analysis_cycle()
    
    print("\n--- Test Complete ---")
    print(f"Final determined sentiment: {sentiment}")

if __name__ == "__main__":
    run_test()
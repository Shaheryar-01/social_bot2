from langdetect import detect
from googletrans import Translator, LANGUAGES
import logging
from dotenv import load_dotenv
import os
import re
logger = logging.getLogger(__name__)

load_dotenv()

class TranslationService:
    def __init__(self):
        self.translator = Translator()
        
        # Initialize OpenAI client only if API key is available
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.openai_client = OpenAI(api_key=api_key)
                self.use_llm = True
                logger.info("OpenAI client initialized for language detection and translation")
            else:
                self.openai_client = None
                self.use_llm = False
                logger.warning("OPENAI_API_KEY not found, using fallback detection only")
        except ImportError:
            self.openai_client = None
            self.use_llm = False
            logger.warning("OpenAI package not installed, using fallback detection only")
    
    def detect_language_with_llm(self, text: str) -> str:
        """Use LLM to accurately detect language including Roman Urdu."""
        if not self.use_llm or not self.openai_client:
            return self.fallback_detection(text)
            
        try:
            prompt = f"""You are a language detection expert. Analyze the following text and determine its language.

Text: "{text}"

Language Detection Rules:
1. If text is STANDARD ENGLISH (proper English words and grammar) → return "en"
2. If text is ROMAN URDU (Urdu/Hindi words written in English letters) → return "ur" 
3. If text is URDU in Arabic script → return "ur"
4. If text is any other language → return the 2-letter ISO code (de, fr, es, ar, etc.)

Examples:
- "what are my last 3 transactions" → "en" (Standard English)
- "check my balance please" → "en" (Standard English)  
- "show me transaction history" → "en" (Standard English)
- "mera balance kya hai" → "ur" (Roman Urdu)
- "account me kitna paisa hai" → "ur" (Roman Urdu)
- "balance check karo" → "ur" (Roman Urdu)
- "wie geht es dir" → "de" (German)

Response format: Return ONLY the 2-letter language code (en, ur, de, fr, etc.). Nothing else."""

            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0
            )
            
            detected_lang = response.choices[0].message.content.strip().lower()
            
            if detected_lang in LANGUAGES or detected_lang == 'ur':
                logger.info(f"LLM detected language '{detected_lang}' for text: '{text}'")
                return detected_lang
            else:
                logger.warning(f"LLM returned invalid language code '{detected_lang}', falling back")
                return self.fallback_detection(text)
                
        except Exception as e:
            logger.error(f"LLM language detection failed: {e}, falling back")
            return self.fallback_detection(text)
    
    def translate_with_llm(self, text: str, source_lang: str, target_lang: str) -> str:
        """Use LLM for accurate translation, especially for Roman Urdu."""
        if not self.use_llm or not self.openai_client:
            return self.translate_with_google(text, source_lang, target_lang)
        
        try:
            # Special handling for Roman Urdu to English
            if source_lang == 'ur' and target_lang == 'en':
                prompt = f"""You are an expert Roman Urdu to English translator. Translate this text accurately while preserving all numbers, names, and banking terms.

    Text to translate: "{text}"

    Translation Rules:
    1. Keep ALL numbers EXACTLY as they are (8 stays 8, never change to 3 or any other number)
    2. Keep banking terms in English: transactions, balance, account, transfer, etc.
    3. Keep proper nouns and names unchanged
    4. Preserve CNIC format: 12345-1234567-1 stays exactly the same
    5. Common Roman Urdu translations:
    - "mera/meri" = "my"
    - "pichli/pichle/akhri" = "last/previous" 
    - "batao/dikhao" = "tell me/show me"
    - "kya hai" = "what is"
    - "kitna" = "how much"
    - "karo" = "do"
    - "check" = "check" (keep as is)

    Examples:
    - "meri pichli 8 transactions batao" → "tell me my last 8 transactions"
    - "balance check karo" → "check my balance"
    - "account me kitna paisa hai" → "how much money is in my account"
    - "42501-5440926-9" → "42501-5440926-9"

    Return ONLY the English translation, nothing else."""

            elif source_lang == 'en' and target_lang == 'ur':
                prompt = f"""You are an expert English to Urdu translator. Translate this COMPLETE English text to natural Urdu while preserving all numbers and technical terms. TRANSLATE THE ENTIRE TEXT - DO NOT TRUNCATE.

    Text to translate: "{text}"

    Translation Rules:
    1. Keep ALL numbers EXACTLY as they are
    2. Keep banking terms in English when commonly used: balance, account, transaction, grocery store, Amazon, Uber, etc.
    3. Use natural Urdu grammar and vocabulary
    4. Preserve proper nouns and CNIC formats
    5. Use Arabic script for Urdu
    6. TRANSLATE THE COMPLETE TEXT - translate every single sentence and detail

    Examples:
    - "tell me my last 8 transactions" → "میری آخری 8 transactions بتائیں"
    - "check my balance" → "میرا balance check کریں"
    - "On June 29, you spent $77.23" → "جون 29 کو، آپ نے $77.23 خرچ کیا"

    IMPORTANT: Translate the ENTIRE text completely. Do not stop in the middle. Include all transactions, all details, all sentences.

    Return ONLY the complete Urdu translation, nothing else."""

            else:
                # For other language pairs, use a general prompt
                prompt = f"""Translate this COMPLETE text from {source_lang} to {target_lang}. Keep all numbers, names, and technical terms exactly as they are. TRANSLATE THE ENTIRE TEXT.

    Text: "{text}"

    Return only the complete translation."""

            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                # NO max_tokens limit - let it translate completely
                temperature=0.1
            )
            
            translated = response.choices[0].message.content.strip()
            
            # Remove quotes if LLM adds them
            if translated.startswith('"') and translated.endswith('"'):
                translated = translated[1:-1]
            
            logger.info(f"LLM translated '{text[:50]}...' from {source_lang} to {target_lang}: '{translated[:100]}...'")
            return translated
            
        except Exception as e:
            logger.error(f"LLM translation failed: {e}, falling back to Google")
            return self.translate_with_google(text, source_lang, target_lang)
    
    def translate_with_google(self, text: str, source_lang: str, target_lang: str) -> str:
        """Fallback Google translation."""
        try:
            result = self.translator.translate(text, src=source_lang, dest=target_lang)
            return result.text
        except Exception as e:
            logger.error(f"Google translation failed: {e}")
            return text
    
    def translate_to_english(self, text: str, source_lang: str) -> str:
        """Enhanced translation to English with LLM priority."""
        try:
            if source_lang == 'en':
                return text
            
            # Don't translate number-only text
            if self.is_number_only_text(text):
                logger.info(f"Skipping translation for number-only text: '{text}'")
                return text
            
            # Use LLM for better translation, especially Roman Urdu
            if self.use_llm and source_lang == 'ur':
                return self.translate_with_llm(text, source_lang, 'en')
            else:
                return self.translate_with_google(text, source_lang, 'en')
            
        except Exception as e:
            logger.error(f"Translation to English failed: {e}")
            return text
    
    def translate_from_english(self, text: str, target_lang: str) -> str:
        """Enhanced translation from English with LLM priority."""
        try:
            if target_lang == 'en':
                return text
            
            # Use LLM for better translation, especially to Urdu
            if self.use_llm and target_lang == 'ur':
                return self.translate_with_llm(text, 'en', target_lang)
            else:
                return self.translate_with_google(text, 'en', target_lang)
            
        except Exception as e:
            logger.error(f"Translation from English failed: {e}")
            return text
    
    def detect_language_smart(self, text: str, sender_id: str = None, get_last_language_func=None) -> str:
        """Smart language detection with LLM priority and number handling."""
        try:
            if len(text.strip()) < 3:
                if sender_id and get_last_language_func:
                    last_lang = get_last_language_func(sender_id)
                    if last_lang != 'en':
                        logger.info(f"Short text detected, using last language: {last_lang}")
                        return last_lang
                return 'en'
            
            # Check if text is number-only
            if self.is_number_only_text(text):
                if sender_id and get_last_language_func:
                    last_lang = get_last_language_func(sender_id)
                    logger.info(f"Number-only text detected: '{text}', using last language: {last_lang}")
                    return last_lang
                else:
                    return 'en'
            
            # Use LLM for detection if available
            if self.use_llm:
                detected = self.detect_language_with_llm(text)
                logger.info(f"LLM detection result: '{detected}' for text: '{text}'")
            else:
                detected = self.fallback_detection(text)
                logger.info(f"Fallback detection result: '{detected}' for text: '{text}'")
            
            if detected in LANGUAGES or detected == 'ur':
                return detected
            else:
                logger.warning(f"Detected language '{detected}' not supported, defaulting to English")
                return 'en'
                
        except Exception as e:
            logger.warning(f"Language detection failed: {e}, defaulting to English")
            return 'en'
    
    def fallback_detection(self, text: str) -> str:
        """Simple fallback using langdetect only."""
        try:
            detected = detect(text)
            if detected in LANGUAGES:
                logger.info(f"Fallback detected language '{detected}' for text: '{text}'")
                return detected
            else:
                return 'en'
        except Exception as e:
            logger.warning(f"Fallback detection failed: {e}, defaulting to English")
            return 'en'

    def is_number_only_text(self, text: str) -> bool:
        """Check if text contains only numbers, spaces, and basic punctuation."""
        clean_text = re.sub(r'[\s\-\.\,\(\)\/]+', '', text)
        return clean_text.isdigit() and len(clean_text) > 0
    
    def get_language_name(self, lang_code: str) -> str:
        """Get human-readable language name."""
        if lang_code == 'ur':
            return 'Urdu/Roman Urdu'
        return LANGUAGES.get(lang_code, lang_code.title())
    
    def get_supported_languages(self) -> dict:
        """Get all supported languages."""
        return LANGUAGES
    
    def detect_language(self, text: str) -> str:
        """Backward compatibility."""
        return self.detect_language_smart(text)

# Global instance
translation_service = TranslationService()
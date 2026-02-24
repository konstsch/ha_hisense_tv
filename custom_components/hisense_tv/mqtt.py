import paho.mqtt.client as mqtt
import sys
import logging

# Настройки
BROKER = "192.168.6.86"
PORT = 36669
USERNAME = "hisenseservice"
PASSWORD = "multimqttservice"
TOPIC = "/remoteapp/tv/remote_service/AutoHTPC/actions/sendkey"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def send_command(cmd):
    """Максимально простой способ отправки"""
    try:
        # Создаем клиент
        client = mqtt.Client(protocol=mqtt.MQTTv311)
        client.username_pw_set(USERNAME, PASSWORD)
        
        # Подключаемся
        logger.info(f"🔄 Подключение к {BROKER}:{PORT}...")
        client.connect(BROKER, PORT, 5)
        
        # Отправляем команду
        logger.info(f"📤 Отправка: {cmd}")
        result = client.publish(TOPIC, cmd, qos=0)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("✅ Команда отправлена")
        else:
            logger.error(f"❌ Ошибка: {result.rc}")
        
        # Завершаем
        client.disconnect()
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "KEY_POWER"
    send_command(cmd)
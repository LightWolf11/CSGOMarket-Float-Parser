import axios from "axios";

export function tg(botToken) {
  const base = `https://api.telegram.org/bot${botToken}`;

  return {
    async sendMessage(chatId, text, replyMarkup = null, parseMode = null) {
      const payload = {
        chat_id: chatId,
        text,
        disable_web_page_preview: true
      };
      if (replyMarkup) payload.reply_markup = replyMarkup; // inline_keyboard [web:37]
      if (parseMode) payload.parse_mode = parseMode;       // HTML/Markdown [web:37]
      await axios.post(`${base}/sendMessage`, payload);
    },

    async editMessageText(chatId, messageId, text, replyMarkup = null, parseMode = null) {
      const payload = {
        chat_id: chatId,
        message_id: messageId,
        text,
        disable_web_page_preview: true
      };
      if (replyMarkup) payload.reply_markup = replyMarkup;
      if (parseMode) payload.parse_mode = parseMode;
      await axios.post(`${base}/editMessageText`, payload); // editMessageText [web:37]
    },

    async getUpdates(offset) {
      return axios.get(`${base}/getUpdates`, { params: { timeout: 25, offset } });
    }
  };
}

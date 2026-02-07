FROM node:18-alpine

WORKDIR /app

# Install dependencies based on package.json
COPY package.json ./
# No lockfile yet, so we use npm install (generated package-lock.json will stay in container)
RUN npm install

# Copy source
COPY . .

# Build (optional here if we dev, but good to have)
# RUN npm run build

# Expose Next.js port
EXPOSE 3000

# Start dev server
CMD ["npm", "run", "dev"]

FROM maven:3.9.11-eclipse-temurin-17 AS build
WORKDIR /build/backend
COPY backend/pom.xml ./pom.xml
RUN mvn -B -q dependency:go-offline
COPY backend/src ./src
COPY web/src ../web/src
RUN mvn -B -q -Dmaven.test.skip=true package
FROM eclipse-temurin:17-jre
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app app && mkdir -p /data/storage && chown -R app:app /data
WORKDIR /app
COPY --from=build /build/backend/target/vietdoc-backend-1.0.0.jar /app/app.jar
USER app
ENV STORAGE_ROOT=/data/storage
ENV DATABASE_URL=jdbc:h2:file:/data/vietdoc
EXPOSE 8080
ENTRYPOINT ["java","-jar","/app/app.jar"]

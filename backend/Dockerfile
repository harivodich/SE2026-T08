FROM maven:3.9.11-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q -Dmaven.test.skip=true package
FROM eclipse-temurin:17-jre
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app app && mkdir -p /data/storage && chown -R app:app /data
WORKDIR /app
COPY --from=build /build/target/vietdoc-backend-1.0.0.jar /app/app.jar
USER app
ENV STORAGE_ROOT=/data/storage
EXPOSE 8080
ENTRYPOINT ["java","-jar","/app/app.jar"]
